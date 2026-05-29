"""
FFmpeg media processing service.
Requires ffmpeg to be installed and available in PATH.

All subprocess calls use bytes mode + explicit utf-8 decode to avoid the
Windows GBK codec crash when filenames or ffmpeg output contain non-ASCII
characters (emoji, CJK, etc.).
"""
import subprocess
import json
import os
import logging

logger = logging.getLogger(__name__)

# Max chunk duration in seconds for STT (wangwangit has 10MB limit)
CHUNK_DURATION = 270  # ~4.5 minutes to stay under 10MB for most audio


# ─────────────────────────────────────────────────────────────────
# Internal subprocess helper — encoding-safe
# ─────────────────────────────────────────────────────────────────

def _run(cmd: list[str], label: str, timeout: int = 600) -> None:
    """
    Run a command, raise RuntimeError on non-zero exit.
    Uses bytes mode to avoid Windows GBK codec errors with non-ASCII paths.
    """
    logger.info(f"{label}: {' '.join(cmd)}")
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"{label} failed:\n{stderr}")


# ─────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────

def extract_audio(input_path: str, output_path: str) -> str:
    """
    Extract mono 16kHz WAV audio from any video/audio file.
    Returns path to the WAV file.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vn",              # No video
        "-acodec", "pcm_s16le",
        "-ar", "16000",     # 16kHz
        "-ac", "1",         # Mono
        output_path,
    ]
    _run(cmd, "FFmpeg audio extraction")
    return output_path


def extract_audio_file(input_path: str, output_path: str) -> str:
    """
    Extract audio from a video file and save as m4a (AAC copy when possible).

    Used when the user UPLOADS a video file: we strip the video track up-front
    so that all downstream processing (cut_segment, STT, VAD) works on a much
    smaller audio-only file instead of the original video.

    Returns path to the audio file.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vn",                  # Drop video stream
        "-acodec", "copy",      # Copy audio codec (no re-encode — fast & lossless)
        output_path,
    ]
    try:
        _run(cmd, "FFmpeg extract audio (copy)")
    except RuntimeError:
        # Fallback: re-encode to AAC if copy fails (e.g. incompatible container)
        logger.warning("Audio copy failed, falling back to AAC re-encode")
        cmd_fallback = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vn",
            "-acodec", "aac",
            "-ab", "192k",
            output_path,
        ]
        _run(cmd_fallback, "FFmpeg extract audio (re-encode AAC)")
    return output_path


def cut_segment(input_path: str, start: float, end: float, output_path: str) -> str:
    """
    Cut a segment from the original media file as 64kbps mono mp3.
    Returns path to the mp3 file.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    duration = end - start
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-ss", str(start),
        "-t", str(duration),
        "-acodec", "libmp3lame",
        "-ab", "64k",
        "-ac", "1",
        output_path,
    ]
    _run(cmd, f"FFmpeg cut segment [{start:.3f}-{end:.3f}]")
    return output_path


def get_duration(input_path: str) -> float:
    """Return media duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        input_path,
    ]
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"ffprobe failed: {stderr}")
    info = json.loads(proc.stdout.decode("utf-8", errors="replace"))
    return float(info["format"]["duration"])


def cut_wav_segment(input_path: str, start: float, end: float, output_path: str) -> str:
    """
    Cut a segment from a WAV file as 16kHz mono WAV (for STT input).
    Returns path to the WAV file.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    duration = end - start
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-ss", str(start),
        "-t", str(duration),
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_path,
    ]
    _run(cmd, f"FFmpeg cut WAV segment [{start:.3f}-{end:.3f}]")
    return output_path


def split_audio_chunks(wav_path: str, chunk_dir: str, chunk_duration: int = CHUNK_DURATION) -> list[str]:
    """
    Split a wav file into chunks of `chunk_duration` seconds.
    Returns sorted list of chunk file paths.
    """
    os.makedirs(chunk_dir, exist_ok=True)
    output_pattern = os.path.join(chunk_dir, "chunk_%03d.wav")
    cmd = [
        "ffmpeg", "-y",
        "-i", wav_path,
        "-f", "segment",
        "-segment_time", str(chunk_duration),
        "-c", "copy",
        output_pattern,
    ]
    _run(cmd, "FFmpeg split into chunks")
    chunks = sorted([
        os.path.join(chunk_dir, f)
        for f in os.listdir(chunk_dir)
        if f.startswith("chunk_") and f.endswith(".wav")
    ])
    return chunks
