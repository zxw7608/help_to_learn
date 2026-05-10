"""
Background worker: polls the SQLite job table and processes pending jobs.
Run with: uv run python backend/worker.py
"""
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlmodel import Session, select

# Ensure project root is in path when running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import settings
from backend.database import engine
from backend.models.job import Job, JobStatus, JobType
from backend.models.material import Material, MaterialStatus, SourceType
from backend.models.segment import Segment, AudioSourceType
from backend.services import downloader, processor, transcriber, tts_service, article_fetcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("worker")

RETRY_DELAY_SECONDS = 30


# ─────────────────────────────────────────────
# Text splitting for article / text materials
# ─────────────────────────────────────────────

def split_text_into_sentences(text: str) -> list[str]:
    """Split text into sentences suitable for TTS."""
    # Split on sentence-ending punctuation or double newlines
    parts = re.split(r'(?<=[.!?])\s+|(?<=[。！？])\s*|[\n]{2,}', text)
    result = []
    for part in parts:
        part = part.strip()
        if len(part) > 5:  # skip very short fragments
            result.append(part)
    return result


# ─────────────────────────────────────────────
# Core pipeline functions
# ─────────────────────────────────────────────

def process_media_material(material: Material, session: Session) -> None:
    """Branch A: upload / url_media — extract audio, cut segments.

    Pipeline:
      1. Download (yt-dlp) — if url_media. Returns subtitle segments if available.
      2. If subtitles found  → use subtitle timestamps to cut video/audio segments directly.
         If no subtitles     → extract mono WAV → STT → cut segments from STT timestamps.
    """
    subtitle_segments: list[dict] = []

    # Step 1: Download if needed
    if material.source_type == SourceType.url_media:
        logger.info(f"Downloading media from: {material.source_url}")
        file_path, subtitle_segments = downloader.download(
            url=material.source_url,
            material_id=material.id,
            user_id=material.user_id,
            base_path=settings.STORAGE_BASE_PATH,
        )
        material.original_file_path = file_path
        # Try to get duration
        try:
            material.duration = processor.get_duration(file_path)
        except Exception:
            pass
        session.add(material)
        session.commit()
    else:
        file_path = material.original_file_path

    if not file_path or not os.path.exists(file_path):
        raise RuntimeError(f"Source file not found: {file_path}")

    audio_dir = os.path.join(settings.STORAGE_BASE_PATH, "audio", str(material.user_id), str(material.id))
    os.makedirs(audio_dir, exist_ok=True)

    # ── Branch A1: Subtitle available — cut directly ──────────────────────────
    if subtitle_segments:
        logger.info(f"Using {len(subtitle_segments)} subtitle segments to cut audio (skip STT)")
        for i, seg_data in enumerate(subtitle_segments, start=1):
            seg_filename = f"seg_{i:03d}.mp3"
            seg_path = os.path.join(audio_dir, seg_filename)
            processor.cut_segment(file_path, seg_data["start"], seg_data["end"], seg_path)

            segment = Segment(
                material_id=material.id,
                user_id=material.user_id,
                index=i,
                start_time=seg_data["start"],
                end_time=seg_data["end"],
                duration=seg_data["end"] - seg_data["start"],
                text=seg_data["text"],
                audio_source_type=AudioSourceType.original,
                audio_file_path=seg_path,
            )
            session.add(segment)

        session.commit()
        logger.info(f"Created {len(subtitle_segments)} segments from subtitles for material {material.id}")
        return

    # ── Branch A2: No subtitle — VAD detect speech, then cut + STT per segment ─
    temp_dir = os.path.join(settings.STORAGE_BASE_PATH, "temp", str(material.user_id), str(material.id))
    os.makedirs(temp_dir, exist_ok=True)
    wav_path = os.path.join(temp_dir, "audio.wav")
    logger.info("No subtitles found — extracting audio to WAV...")
    processor.extract_audio(file_path, wav_path)

    # Use user's token if set, fall back to global
    with Session(engine) as s:
        from backend.models.user import User
        user = s.get(User, material.user_id)
        token = (user.tts_token if user and user.tts_token else None) or settings.TTS_TOKEN
        worker_url = (user.tts_worker_url if user else None) or settings.TTS_WORKER_URL

    # Step 3: Detect speech segments with Silero VAD
    logger.info("Running Silero VAD on audio...")
    from backend.services import vad as vad_service
    vad_segments = vad_service.detect_speech_segments(wav_path)

    if not vad_segments:
        # Fallback: STT on the whole audio (original behavior)
        logger.warning("VAD found no speech — falling back to full-audio STT")
        chunk_dir = os.path.join(temp_dir, "chunks")
        segments_data = transcriber.transcribe(wav_path, worker_url, token, chunk_dir=chunk_dir)
        if not segments_data:
            raise RuntimeError("STT returned no segments")
        for i, seg_data in enumerate(segments_data, start=1):
            seg_filename = f"seg_{i:03d}.mp3"
            seg_path = os.path.join(audio_dir, seg_filename)
            processor.cut_segment(file_path, seg_data["start"], seg_data["end"], seg_path)
            segment = Segment(
                material_id=material.id,
                user_id=material.user_id,
                index=i,
                start_time=seg_data["start"],
                end_time=seg_data["end"],
                duration=seg_data["end"] - seg_data["start"],
                text=seg_data["text"],
                audio_source_type=AudioSourceType.original,
                audio_file_path=seg_path,
            )
            session.add(segment)
        session.commit()
        logger.info(f"Created {len(segments_data)} segments (via fallback STT) for material {material.id}")
    else:
        # Step 4: For each VAD segment, cut WAV chunk → STT → cut MP3 from original
        chunks_dir = os.path.join(temp_dir, "vad_chunks")
        os.makedirs(chunks_dir, exist_ok=True)
        for i, vad in enumerate(vad_segments, start=1):
            # Cut WAV chunk for STT
            wav_chunk_path = os.path.join(chunks_dir, f"chunk_{i:03d}.wav")
            processor.cut_wav_segment(wav_path, vad["start"], vad["end"], wav_chunk_path)

            # Transcribe the chunk
            try:
                chunk_segs = transcriber.transcribe(wav_chunk_path, worker_url, token)
            except Exception as e:
                logger.error(f"STT failed for VAD segment {i} [{vad['start']:.1f}-{vad['end']:.1f}]: {e}")
                chunk_segs = []

            # Build text from STT results (offset timestamps to absolute positions)
            text = " ".join(s.get("text", "") for s in (chunk_segs or [])).strip()

            # Clean up WAV chunk
            try:
                os.remove(wav_chunk_path)
            except OSError:
                pass

            # Cut MP3 segment from original media for playback
            seg_filename = f"seg_{i:03d}.mp3"
            seg_path = os.path.join(audio_dir, seg_filename)
            processor.cut_segment(file_path, vad["start"], vad["end"], seg_path)

            segment = Segment(
                material_id=material.id,
                user_id=material.user_id,
                index=i,
                start_time=vad["start"],
                end_time=vad["end"],
                duration=vad["end"] - vad["start"],
                text=text,
                audio_source_type=AudioSourceType.original,
                audio_file_path=seg_path,
            )
            session.add(segment)

        session.commit()
        logger.info(f"Created {len(vad_segments)} segments (via VAD+STT) for material {material.id}")

    # Clean up temp files
    try:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass



def process_text_material(material: Material, session: Session) -> None:
    """Branch B: url_article / text — fetch text if needed, TTS each sentence."""
    # Step 1: Fetch article if URL
    if material.source_type == SourceType.url_article:
        logger.info(f"Fetching article: {material.source_url}")
        raw_text = article_fetcher.fetch(material.source_url)
        material.raw_text = raw_text
        session.add(material)
        session.commit()
    else:
        raw_text = material.raw_text

    if not raw_text or not raw_text.strip():
        raise RuntimeError("No text content found")

    # Step 2: Split into sentences
    sentences = split_text_into_sentences(raw_text)
    if not sentences:
        raise RuntimeError("Could not split text into sentences")

    # Step 3: TTS each sentence
    audio_dir = os.path.join(settings.STORAGE_BASE_PATH, "audio", str(material.user_id), str(material.id))
    os.makedirs(audio_dir, exist_ok=True)

    with Session(engine) as s:
        from backend.models.user import User
        user = s.get(User, material.user_id)
        worker_url = (user.tts_worker_url if user else None) or settings.TTS_WORKER_URL

    # Pick a random voice for this entire material to keep it consistent within segments
    selected_voice = tts_service.get_random_voice(material.language)
    logger.info(f"Selected random voice for material {material.id}: {selected_voice}")

    for i, sentence in enumerate(sentences, start=1):
        seg_filename = f"seg_{i:03d}.mp3"
        seg_path = os.path.join(audio_dir, seg_filename)
        logger.info(f"TTS segment {i}/{len(sentences)} using voice {selected_voice}")
        tts_service.synthesize(sentence, seg_path, worker_url, voice=selected_voice)

        segment = Segment(
            material_id=material.id,
            user_id=material.user_id,
            index=i,
            start_time=None,
            end_time=None,
            duration=None,
            text=sentence,
            audio_source_type=AudioSourceType.tts,
            audio_file_path=seg_path,
        )
        session.add(segment)

    session.commit()
    logger.info(f"Created {len(sentences)} TTS segments for material {material.id}")


def process_material(material_id: int) -> None:
    with Session(engine) as session:
        material = session.get(Material, material_id)
        if not material:
            raise ValueError(f"Material {material_id} not found")

        material.status = MaterialStatus.processing
        material.updated_at = datetime.utcnow()
        session.add(material)
        session.commit()

        try:
            if material.source_type in (SourceType.upload, SourceType.url_media):
                process_media_material(material, session)
            else:
                process_text_material(material, session)

            material.status = MaterialStatus.done
            material.updated_at = datetime.utcnow()
            session.add(material)
            session.commit()
            logger.info(f"Material {material_id} processing DONE")

        except Exception as e:
            logger.error(f"Material {material_id} processing FAILED: {e}", exc_info=True)
            material.status = MaterialStatus.failed
            material.error_msg = str(e)[:2000]
            material.updated_at = datetime.utcnow()
            session.add(material)
            session.commit()
            raise


# ─────────────────────────────────────────────
# Job dispatcher (with concurrent execution support)
# ─────────────────────────────────────────────

_MAX_CONCURRENT_JOBS = 4    # Max simultaneous material processing jobs
_executor = ThreadPoolExecutor(max_workers=_MAX_CONCURRENT_JOBS)
_futures: dict[int, Future] = {}  # job_id -> Future


def _execute_job(job_id: int, job_type, job_payload: str) -> None:
    """Execute a single job (runs in a thread pool worker)."""
    try:
        payload = json.loads(job_payload)

        if job_type == JobType.process_material:
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
        logger.error(f"Job {job_id} failed: {e}")
        with Session(engine) as session:
            db_job = session.get(Job, job_id)
            if db_job:
                db_job.retry_count += 1
                if db_job.retry_count >= db_job.max_retries:
                    db_job.status = JobStatus.failed
                    db_job.error_msg = str(e)[:2000]
                    logger.error(f"Job {job_id} permanently failed after {db_job.retry_count} retries")
                else:
                    db_job.status = JobStatus.pending
                    db_job.run_at = datetime.utcnow() + timedelta(seconds=RETRY_DELAY_SECONDS)
                    logger.warning(
                        f"Job {job_id} will retry in {RETRY_DELAY_SECONDS}s "
                        f"(attempt {db_job.retry_count}/{db_job.max_retries})"
                    )
                db_job.updated_at = datetime.utcnow()
                session.add(db_job)
                session.commit()
    finally:
        _futures.pop(job_id, None)


def _cleanup_completed_futures() -> None:
    """Remove completed futures from the tracking dict."""
    done_ids = [jid for jid, fut in _futures.items() if fut.done()]
    for jid in done_ids:
        _futures.pop(jid, None)


def poll_and_process() -> None:
    """Poll pending jobs and dispatch them to the thread pool (up to max concurrent)."""
    _cleanup_completed_futures()

    # How many slots are available
    available_slots = _MAX_CONCURRENT_JOBS - len(_futures)
    if available_slots <= 0:
        return

    with Session(engine) as session:
        now = datetime.utcnow()
        # Pick up as many pending jobs as we have slots for
        jobs = session.exec(
            select(Job)
            .where(Job.status == JobStatus.pending, Job.run_at <= now)
            .order_by(Job.created_at)
            .limit(available_slots)
        ).all()

        if not jobs:
            return

        for job in jobs:
            logger.info(f"Picked up job {job.id} type={job.job_type}")
            job.status = JobStatus.running
            job.updated_at = now
            session.add(job)

            # Submit to thread pool
            fut = _executor.submit(_execute_job, job.id, job.job_type, job.payload)
            _futures[job.id] = fut

        session.commit()



# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def recover_orphaned_jobs() -> None:
    """
    On startup: reset any jobs stuck in 'running' state back to 'pending'.
    These are jobs that were mid-execution when the worker was killed or restarted.
    Also reset the associated Material status back to 'pending'.
    """
    with Session(engine) as session:
        orphaned = session.exec(
            select(Job).where(Job.status == JobStatus.running)
        ).all()

        if not orphaned:
            return

        logger.warning(f"Found {len(orphaned)} orphaned running job(s) — resetting to pending")
        for job in orphaned:
            job.status = JobStatus.pending
            job.run_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            session.add(job)

            # Also reset the Material status so UI shows correct state
            try:
                payload = json.loads(job.payload)
                material_id = payload.get("material_id")
                if material_id:
                    material = session.get(Material, material_id)
                    if material and material.status == MaterialStatus.processing:
                        material.status = MaterialStatus.pending
                        material.updated_at = datetime.utcnow()
                        session.add(material)
                        logger.info(f"  Reset material {material_id} status: processing → pending")
            except Exception as ex:
                logger.warning(f"  Could not reset material for job {job.id}: {ex}")

        session.commit()
        logger.info("Orphaned jobs recovered. They will be retried now.")


if __name__ == "__main__":

    # Create storage directories
    for sub in ("originals", "audio", "temp"):
        os.makedirs(os.path.join(settings.STORAGE_BASE_PATH, sub), exist_ok=True)

    # Recover any jobs that were left in 'running' state from a previous crash
    recover_orphaned_jobs()

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        poll_and_process,
        "interval",
        seconds=settings.JOB_POLL_INTERVAL,
        max_instances=5,  # Allow concurrent polls so new jobs can be picked up while others run
    )

    logger.info(f"Worker started. Polling every {settings.JOB_POLL_INTERVAL}s (max {_MAX_CONCURRENT_JOBS} concurrent jobs)...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker stopped.")

