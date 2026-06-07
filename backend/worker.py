"""
Core material processing logic.

This module contains all the business functions for processing materials
(process_media_material, process_text_material, process_material).

Job scheduling and dispatch are handled by backend.job_runner, which runs
an in-process ThreadPoolExecutor inside the FastAPI process.
This file is NOT run as a standalone process anymore.
"""
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta

from sqlmodel import Session, select

# Ensure project root is in path when running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import settings
from backend.database import engine
from backend.models.job import Job, JobStatus, JobType
from backend.models.material import Material, MaterialStatus, SourceType
from backend.models.segment import Segment, AudioSourceType
from backend.services import downloader, processor, transcriber, tts_service, article_fetcher

logger = logging.getLogger(__name__)

RETRY_DELAY_SECONDS = 30


def _read_stt_setting(session, key: str, default: str = "") -> str:
    """Read a single STT-related setting from system_settings, falling back to default."""
    from backend.models.system_setting import SystemSetting
    row = session.get(SystemSetting, key)
    return row.value if row else default


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
        # Look up user for per-user proxy / cookie settings
        from backend.models.user import User
        user = session.get(User, material.user_id)
        logger.info(f"Downloading media from: {material.source_url}")
        file_path, subtitle_segments = downloader.download(
            url=material.source_url,
            material_id=material.id,
            user_id=material.user_id,
            base_path=settings.STORAGE_BASE_PATH,
            http_proxy=user.http_proxy if user else None,
            ytdlp_proxy=user.ytdlp_proxy if user else None,
            ytdlp_cookies=user.ytdlp_cookies if user else None,
        )
        material.original_file_path = file_path
        # Try to get duration
        try:
            material.duration = processor.get_duration(file_path)
        except Exception:
            pass
        session.add(material)
        session.commit()
        # yt-dlp already downloaded audio-only; use it directly
        audio_path = file_path
    else:
        file_path = material.original_file_path
        # ── Validate before touching the file ──────────────────────────────────
        # original_file_path can be None if the upload record was created but the
        # file was never actually saved (e.g. a failed/interrupted upload).
        if not file_path or not os.path.exists(file_path):
            raise RuntimeError(f"Uploaded file not found: {file_path!r} — the upload may have failed")
        # ── Uploaded video: extract audio track first ──────────────────────────
        # Strip the video stream so all downstream FFmpeg/VAD/STT work on a
        # much smaller audio-only file.
        originals_dir = os.path.join(
            settings.STORAGE_BASE_PATH, "originals",
            str(material.user_id), str(material.id),
        )
        os.makedirs(originals_dir, exist_ok=True)
        audio_path = os.path.join(originals_dir, "audio.m4a")
        logger.info(f"Extracting audio from uploaded file: {file_path} → {audio_path}")
        processor.extract_audio_file(file_path, audio_path)
        logger.info(f"Audio extracted: {audio_path}")

    if not file_path or not os.path.exists(file_path):
        raise RuntimeError(f"Source file not found: {file_path}")


    audio_dir = os.path.join(settings.STORAGE_BASE_PATH, "audio", str(material.user_id), str(material.id))
    os.makedirs(audio_dir, exist_ok=True)

    # ── Branch A1: Subtitle available — cut directly ──────────────────────────
    if subtitle_segments:
        logger.info(f"Using {len(subtitle_segments)} subtitle segments to cut audio (skip STT)")
        segs_to_add = []
        for i, seg_data in enumerate(subtitle_segments, start=1):
            seg_filename = f"seg_{i:03d}.mp3"
            seg_path = os.path.join(audio_dir, seg_filename)
            processor.cut_segment(audio_path, seg_data["start"], seg_data["end"], seg_path)

            segs_to_add.append(Segment(
                material_id=material.id,
                user_id=material.user_id,
                index=i,
                start_time=seg_data["start"],
                end_time=seg_data["end"],
                duration=seg_data["end"] - seg_data["start"],
                text=seg_data["text"],
                audio_source_type=AudioSourceType.original,
                audio_file_path=seg_path,
            ))

        # Use a short independent session so the write lock is held only during commit.
        with Session(engine) as s:
            s.add_all(segs_to_add)
            s.commit()
        logger.info(f"Created {len(subtitle_segments)} segments from subtitles for material {material.id}")
        return

    # ── Branch A2: No subtitle — VAD detect speech, then cut + STT per segment ─
    temp_dir = os.path.join(settings.STORAGE_BASE_PATH, "temp", str(material.user_id), str(material.id))
    os.makedirs(temp_dir, exist_ok=True)
    wav_path = os.path.join(temp_dir, "audio.wav")
    logger.info("No subtitles found — extracting audio to WAV...")
    processor.extract_audio(audio_path, wav_path)

    # Use user's token if set, fall back to global
    with Session(engine) as s:
        from backend.models.user import User
        from backend.models.system_setting import SystemSetting
        user = s.get(User, material.user_id)
        token = (user.tts_token if user and user.tts_token else None) or settings.TTS_TOKEN
        worker_url = (user.tts_worker_url if user else None) or settings.TTS_WORKER_URL

        # Read STT admin settings
        stt_backend = _read_stt_setting(s, "stt_backend", settings.STT_BACKEND)
        stt_max_fail = int(_read_stt_setting(s, "stt_max_consecutive_failures", str(settings.STT_MAX_CONSECUTIVE_FAILURES)))
        stt_whisper_model = _read_stt_setting(s, "stt_whisper_model_path", settings.STT_WHISPER_MODEL_PATH)

    # Step 3: Detect speech segments with Silero VAD
    logger.info("Running Silero VAD on audio...")
    from backend.services import vad as vad_service
    vad_segments = vad_service.detect_speech_segments(wav_path)

    # Pre-load whisper model once for the whole job (reused across all chunks)
    # to avoid re-loading 200 MB per chunk.
    _whisper_model_instance = None
    if stt_backend == "whisper_cpp":
        from whisper_cpp_python import Whisper
        logger.info(f"Pre-loading whisper model for job: {stt_whisper_model or 'ggml-base.bin'}")
        _whisper_model_instance = Whisper(
            model_path=stt_whisper_model or "ggml-base.bin",
            n_threads=2,
        )

    try:
        if not vad_segments:
            # Fallback: STT on the whole audio (original behavior)
            logger.warning("VAD found no speech — falling back to full-audio STT")
            chunk_dir = os.path.join(temp_dir, "chunks")
            segments_data = transcriber.transcribe(
                wav_path, worker_url, token, chunk_dir=chunk_dir,
                http_proxy=user.http_proxy if user else None,
                https_proxy=user.https_proxy if user else None,
                backend=stt_backend,
                whisper_model_path=stt_whisper_model,
                whisper_model=_whisper_model_instance,
            )
            if not segments_data:
                raise RuntimeError("STT returned no segments")
            segs_to_add = []
            for i, seg_data in enumerate(segments_data, start=1):
                seg_filename = f"seg_{i:03d}.mp3"
                seg_path = os.path.join(audio_dir, seg_filename)
                processor.cut_segment(audio_path, seg_data["start"], seg_data["end"], seg_path)
                segs_to_add.append(Segment(
                    material_id=material.id,
                    user_id=material.user_id,
                    index=i,
                    start_time=seg_data["start"],
                    end_time=seg_data["end"],
                    duration=seg_data["end"] - seg_data["start"],
                    text=seg_data["text"],
                    audio_source_type=AudioSourceType.original,
                    audio_file_path=seg_path,
                ))
            with Session(engine) as s:
                s.add_all(segs_to_add)
                s.commit()
            logger.info(f"Created {len(segments_data)} segments (via fallback STT) for material {material.id}")
        else:
            # Step 4: For each VAD segment, cut WAV chunk → STT → cut MP3 from original
            chunks_dir = os.path.join(temp_dir, "vad_chunks")
            os.makedirs(chunks_dir, exist_ok=True)
            consecutive_failures = 0
            skipped = False
            pending_segs: list[Segment] = []
            for i, vad in enumerate(vad_segments, start=1):
                # Cut WAV chunk for STT
                wav_chunk_path = os.path.join(chunks_dir, f"chunk_{i:03d}.wav")
                processor.cut_wav_segment(wav_path, vad["start"], vad["end"], wav_chunk_path)

                if skipped:
                    # Already skipping — just create empty segment
                    chunk_segs = []
                else:
                    # Transcribe the chunk
                    try:
                        chunk_segs = transcriber.transcribe(
                            wav_chunk_path, worker_url, token,
                            http_proxy=user.http_proxy if user else None,
                            https_proxy=user.https_proxy if user else None,
                            backend=stt_backend,
                            whisper_model_path=stt_whisper_model,
                            whisper_model=_whisper_model_instance,
                        )
                        consecutive_failures = 0  # reset on success
                    except Exception as e:
                        logger.error(f"STT failed for VAD segment {i} [{vad['start']:.1f}-{vad['end']:.1f}]: {e}")
                        chunk_segs = []
                        consecutive_failures += 1
                        if consecutive_failures >= stt_max_fail:
                            logger.warning(
                                f"STT: {consecutive_failures} consecutive failures reached threshold {stt_max_fail} — "
                                f"skipping remaining {len(vad_segments) - i} segments"
                            )
                            skipped = True

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
                processor.cut_segment(audio_path, vad["start"], vad["end"], seg_path)

                pending_segs.append(Segment(
                    material_id=material.id,
                    user_id=material.user_id,
                    index=i,
                    start_time=vad["start"],
                    end_time=vad["end"],
                    duration=vad["end"] - vad["start"],
                    text=text,
                    audio_source_type=AudioSourceType.original,
                    audio_file_path=seg_path,
                ))
                # Flush to DB every 10 segments to keep memory bounded
                if len(pending_segs) >= 10:
                    with Session(engine) as s:
                        s.add_all(pending_segs)
                        s.commit()
                    pending_segs.clear()

        # Flush any remaining segments
        if pending_segs:
            with Session(engine) as s:
                s.add_all(pending_segs)
                s.commit()
        logger.info(f"Created {len(vad_segments)} segments (via VAD+STT) for material {material.id}")

    finally:
        # Explicitly release the whisper model to reclaim ~200 MB immediately.
        # whisper_cpp_python holds native C++ memory; del + gc.collect() ensures
        # the destructor runs before the next job starts (or the thread goes idle).
        if _whisper_model_instance is not None:
            del _whisper_model_instance
            _whisper_model_instance = None
            import gc
            gc.collect()
            logger.info("Whisper model released (memory reclaimed)")

    # Clean up temp files
    try:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass



def process_text_material(material: Material) -> None:
    """Branch B: url_article / text — fetch text if needed, TTS each sentence."""
    # Look up user settings (proxy, worker) once
    with Session(engine) as s:
        from backend.models.user import User
        user = s.get(User, material.user_id)
        worker_url = (user.tts_worker_url if user else None) or settings.TTS_WORKER_URL
        http_proxy = user.http_proxy if user else None
        https_proxy = user.https_proxy if user else None

    # Step 1: Fetch article if URL
    if material.source_type == SourceType.url_article:
        logger.info(f"Fetching article: {material.source_url}")
        raw_text = article_fetcher.fetch(material.source_url,
                                          http_proxy=http_proxy,
                                          https_proxy=https_proxy)
        # Persist raw_text using a short session
        with Session(engine) as s:
            mat = s.get(Material, material.id)
            if mat:
                mat.raw_text = raw_text
                s.add(mat)
                s.commit()
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

    # Pick a random voice for this entire material to keep it consistent within segments
    selected_voice = tts_service.get_random_voice(material.language)
    logger.info(f"Selected random voice for material {material.id}: {selected_voice}")

    segs_to_add = []
    for i, sentence in enumerate(sentences, start=1):
        seg_filename = f"seg_{i:03d}.mp3"
        seg_path = os.path.join(audio_dir, seg_filename)
        logger.info(f"TTS segment {i}/{len(sentences)} using voice {selected_voice}")
        tts_service.synthesize(sentence, seg_path, worker_url, voice=selected_voice,
                               http_proxy=http_proxy, https_proxy=https_proxy)

        segs_to_add.append(Segment(
            material_id=material.id,
            user_id=material.user_id,
            index=i,
            start_time=None,
            end_time=None,
            duration=None,
            text=sentence,
            audio_source_type=AudioSourceType.tts,
            audio_file_path=seg_path,
        ))

    with Session(engine) as s:
        s.add_all(segs_to_add)
        s.commit()
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
                process_text_material(material)

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
    print(
        "worker.py is no longer run as a standalone process.\n"
        "Job execution is handled by backend.job_runner inside the FastAPI process.\n"
        "Start the application with: uv run uvicorn backend.main:app"
    )
