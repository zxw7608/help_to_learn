"""
Global in-process job runner.

Replaces the standalone worker process + poll_and_process() scheduler.
The runner is started once in FastAPI's lifespan and lives for the entire
process lifetime.  API routes submit jobs directly via job_runner.submit().

Design:
  - Single ThreadPoolExecutor shared across the whole application.
  - One Future per job; duplicate submits for the same job_id are rejected.
  - On startup:
      1. Orphaned "running" jobs are reset to "pending" and re-queued.
      2. All existing "pending" jobs are immediately submitted (handles restarts).
  - A background polling thread runs every POLL_INTERVAL seconds to pick up
    any pending jobs that were missed or became ready after a retry delay.
  - On shutdown, the executor waits for all running jobs to finish (graceful).
"""
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Maximum simultaneous material processing jobs
MAX_CONCURRENT_JOBS = 4

# Seconds before a failed job may be retried
RETRY_DELAY_SECONDS = 30

# Background polling interval (seconds) — fallback sweep for missed/retry jobs
POLL_INTERVAL = 15


class JobRunner:
    """Singleton in-process job executor."""

    def __init__(self, max_workers: int = MAX_CONCURRENT_JOBS):
        self._max_workers = max_workers
        self._executor: ThreadPoolExecutor | None = None
        self._futures: dict[int, Future] = {}  # job_id -> Future
        self._stop_event = threading.Event()
        self._poll_thread: threading.Thread | None = None

    # ─────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────

    def startup(self) -> None:
        """Call once from FastAPI lifespan startup."""
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="job-worker",
        )
        logger.info(f"JobRunner started (max_workers={self._max_workers})")

        # Step 1: Reset orphaned running jobs → pending, then submit them
        self._recover_orphaned_jobs()

        # Step 2: Submit all pre-existing pending jobs (e.g. from before restart)
        # self._submit_all_pending()

        # Step 3: Start background sweep thread for retry/missed jobs
        self._stop_event.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            name="job-runner-poll",
            daemon=True,
        )
        self._poll_thread.start()
        logger.info(f"JobRunner poll thread started (interval={POLL_INTERVAL}s)")

    def shutdown(self) -> None:
        """Call once from FastAPI lifespan shutdown — waits for running jobs."""
        logger.info("JobRunner shutting down — waiting for running jobs...")
        self._stop_event.set()
        if self._poll_thread:
            self._poll_thread.join(timeout=5)
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None
        logger.info("JobRunner stopped.")

    # ─────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────

    def submit(self, material_id: int) -> None:
        """
        Look up the pending job for *material_id* and submit it to the
        thread pool.  Safe to call from any thread / async context.
        """
        if self._executor is None:
            logger.error("JobRunner not started — cannot submit job")
            return

        from backend.database import engine
        from backend.models.job import Job, JobStatus, JobType
        from sqlmodel import Session, select

        with Session(engine) as session:
            job = session.exec(
                select(Job)
                .where(
                    Job.job_type == JobType.process_material,
                    Job.status == JobStatus.pending,
                    Job.payload.contains(f'"material_id": {material_id}'),
                )
                .order_by(Job.created_at.desc())
            ).first()

            if not job:
                logger.warning(
                    f"submit: no pending job found for material_id={material_id}"
                )
                return

            self._submit_job(session, job)

    # ─────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────

    def _submit_job(self, session, job) -> bool:
        """
        Mark *job* as running and enqueue it.  Returns True if submitted,
        False if already queued or executor not available.
        Must be called with an open Session holding *job*.
        """
        from backend.models.job import JobStatus

        self._cleanup_completed_futures()
        if job.id in self._futures:
            return False  # already running

        if self._executor is None:
            return False

        job.status = JobStatus.running
        job.updated_at = datetime.utcnow()
        session.add(job)
        session.commit()

        # Snapshot values before session closes
        job_id = job.id
        job_type = job.job_type
        job_payload = job.payload

        fut = self._executor.submit(self._execute_job, job_id, job_type, job_payload)
        self._futures[job_id] = fut
        logger.info(f"Job {job_id} submitted (payload={job_payload!r})")
        return True

    def _cleanup_completed_futures(self) -> None:
        done = [jid for jid, f in self._futures.items() if f.done()]
        for jid in done:
            self._futures.pop(jid, None)

    def _submit_all_pending(self) -> None:
        """
        Submit every job that is currently in 'pending' state and whose
        run_at timestamp is in the past.  Called once at startup to resume
        any jobs that existed before the process was (re)started.
        """
        from backend.database import engine
        from backend.models.job import Job, JobStatus
        from sqlmodel import Session, select

        with Session(engine) as session:
            now = datetime.utcnow()
            pending = session.exec(
                select(Job)
                .where(Job.status == JobStatus.pending, Job.run_at <= now)
                .order_by(Job.created_at)
            ).all()

            if not pending:
                logger.info("No pending jobs to resume at startup.")
                return

            logger.info(f"Resuming {len(pending)} pending job(s) from DB...")
            submitted = 0
            for job in pending:
                if len(self._futures) >= self._max_workers:
                    logger.info(
                        f"Thread pool full — {len(pending) - submitted} pending job(s) "
                        "will be picked up by the poll loop."
                    )
                    break
                if self._submit_job(session, job):
                    submitted += 1
            logger.info(f"Resumed {submitted} pending job(s).")

    def _poll_loop(self) -> None:
        """
        Background thread: periodically sweep for pending jobs that are ready
        to run (covers retry-delayed jobs and any jobs missed at startup due to
        a full thread pool).
        """
        while not self._stop_event.wait(POLL_INTERVAL):
            try:
                self._sweep_pending()
            except Exception as exc:
                logger.error(f"Poll loop error: {exc}", exc_info=True)

    def _sweep_pending(self) -> None:
        """Pick up any pending jobs that are ready and have free executor slots."""
        if self._executor is None:
            return

        self._cleanup_completed_futures()
        available = self._max_workers - len(self._futures)
        if available <= 0:
            return

        from backend.database import engine
        from backend.models.job import Job, JobStatus
        from sqlmodel import Session, select

        with Session(engine) as session:
            now = datetime.utcnow()
            pending = session.exec(
                select(Job)
                .where(Job.status == JobStatus.pending, Job.run_at <= now)
                .order_by(Job.created_at)
                .limit(available)
            ).all()

            if not pending:
                return

            for job in pending:
                if self._submit_job(session, job):
                    logger.info(f"Poll loop picked up job {job.id}")

    def _execute_job(self, job_id: int, job_type, job_payload: str) -> None:
        """Runs inside a worker thread."""
        from backend.database import engine
        from backend.models.job import Job, JobStatus
        from backend.worker import process_material
        from sqlmodel import Session

        try:
            payload = json.loads(job_payload)
            if job_type.value == "process_material" or str(job_type) in (
                "process_material",
                "JobType.process_material",
            ):
                process_material(payload["material_id"])

            with Session(engine) as session:
                db_job = session.get(Job, job_id)
                if db_job:
                    db_job.status = JobStatus.done
                    db_job.updated_at = datetime.utcnow()
                    session.add(db_job)
                    session.commit()
            logger.info(f"Job {job_id} completed")

        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)
            from backend.database import engine as _engine
            from backend.models.job import Job as _Job, JobStatus as _JS
            from sqlmodel import Session as _S

            with _S(_engine) as session:
                db_job = session.get(_Job, job_id)
                if db_job:
                    db_job.retry_count += 1
                    if db_job.retry_count >= db_job.max_retries:
                        db_job.status = _JS.failed
                        db_job.error_msg = str(e)[:2000]
                        logger.error(
                            f"Job {job_id} permanently failed after "
                            f"{db_job.retry_count} retries"
                        )
                    else:
                        db_job.status = _JS.pending
                        db_job.run_at = datetime.utcnow() + timedelta(
                            seconds=RETRY_DELAY_SECONDS
                        )
                        logger.warning(
                            f"Job {job_id} will retry in {RETRY_DELAY_SECONDS}s "
                            f"(attempt {db_job.retry_count}/{db_job.max_retries})"
                        )
                    db_job.updated_at = datetime.utcnow()
                    session.add(db_job)
                    session.commit()
        finally:
            self._futures.pop(job_id, None)

    def _recover_orphaned_jobs(self) -> None:
        """
        On startup: reset any jobs stuck in 'running' state back to 'pending'.
        These are jobs that were mid-execution when the process was killed or restarted.
        Also reset the associated Material status back to 'pending'.
        """
        from backend.database import engine
        from backend.models.job import Job, JobStatus
        from backend.models.material import Material, MaterialStatus
        from sqlmodel import Session, select

        with Session(engine) as session:
            orphaned = session.exec(
                select(Job).where(Job.status == JobStatus.running)
            ).all()

            if not orphaned:
                return

            logger.warning(
                f"Found {len(orphaned)} orphaned running job(s) — resetting to pending"
            )
            for job in orphaned:
                job.status = JobStatus.pending
                job.run_at = datetime.utcnow()
                job.updated_at = datetime.utcnow()
                session.add(job)

                try:
                    payload = json.loads(job.payload)
                    material_id = payload.get("material_id")
                    if material_id:
                        material = session.get(Material, material_id)
                        if material and material.status == MaterialStatus.processing:
                            material.status = MaterialStatus.pending
                            material.updated_at = datetime.utcnow()
                            session.add(material)
                            logger.info(
                                f"  Reset material {material_id} status: processing → pending"
                            )
                except Exception as ex:
                    logger.warning(
                        f"  Could not reset material for job {job.id}: {ex}"
                    )

            session.commit()
            logger.info(
                f"Orphaned jobs reset to pending — will be picked up by _submit_all_pending."
            )


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton — import this everywhere
# ─────────────────────────────────────────────────────────────────────────────

job_runner = JobRunner(max_workers=MAX_CONCURRENT_JOBS)
