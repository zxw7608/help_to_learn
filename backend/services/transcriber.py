"""
STT transcription service using wangwangit/tts worker.
Endpoint: POST /v1/audio/transcriptions
Wraps SiliconFlow FunAudioLLM/SenseVoiceSmall (OpenAI-compatible format).
Handles large files by chunking them first.
"""
import httpx
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Max file size before chunking (bytes) — worker limit is 10MB
MAX_FILE_SIZE = 9 * 1024 * 1024  # 9MB safety margin


def transcribe(
    wav_path: str,
    worker_url: str,
    token: Optional[str] = None,
    chunk_dir: Optional[str] = None,
    http_proxy: Optional[str] = None,
    https_proxy: Optional[str] = None,
) -> list[dict]:
    """
    Transcribe an audio file. Returns list of segments:
    [{"start": float, "end": float, "text": str}, ...]

    If the file is too large, splits into chunks first and offsets timestamps.
    """
    file_size = os.path.getsize(wav_path)

    if file_size <= MAX_FILE_SIZE:
        return _transcribe_file(wav_path, worker_url, token, time_offset=0.0,
                                http_proxy=http_proxy, https_proxy=https_proxy)

    # Large file: split into chunks
    if chunk_dir is None:
        chunk_dir = os.path.join(os.path.dirname(wav_path), "chunks")

    from backend.services.processor import split_audio_chunks, get_duration
    chunks = split_audio_chunks(wav_path, chunk_dir)

    all_segments = []
    time_offset = 0.0

    for chunk_path in chunks:
        try:
            chunk_duration = get_duration(chunk_path)
            segs = _transcribe_file(chunk_path, worker_url, token, time_offset=time_offset,
                                    http_proxy=http_proxy, https_proxy=https_proxy)
            all_segments.extend(segs)
            time_offset += chunk_duration
        except Exception as e:
            logger.error(f"Chunk {chunk_path} transcription failed: {e}")
            raise
        finally:
            try:
                os.remove(chunk_path)
            except OSError:
                pass

    return all_segments


def _transcribe_file(
    audio_path: str,
    worker_url: str,
    token: Optional[str],
    time_offset: float = 0.0,
    http_proxy: Optional[str] = None,
    https_proxy: Optional[str] = None,
) -> list[dict]:
    """Call the STT API and parse the response. Returns segments with adjusted timestamps."""
    from backend.services.proxy import build_proxies

    url = f"{worker_url.rstrip('/')}/v1/audio/transcriptions"

    with open(audio_path, "rb") as f:
        files = {"file": (os.path.basename(audio_path), f, "audio/wav")}
        data = {"response_format": "verbose_json"}
        if token:
            data["token"] = token

        proxies = build_proxies(http_proxy, https_proxy)

        logger.info(f"Calling STT API: {url}" + (f" via proxy {proxies}" if proxies else ""))
        client_kwargs = {"proxies": proxies} if proxies else {}
        with httpx.Client(**client_kwargs) as client:
            response = client.post(url, files=files, data=data, timeout=300)

    if response.status_code != 200:
        raise RuntimeError(f"STT API error {response.status_code}: {response.text}")

    result = response.json()

    # Parse verbose_json format (OpenAI-compatible)
    segments = result.get("segments", [])
    if segments:
        return [
            {
                "start": seg["start"] + time_offset,
                "end": seg["end"] + time_offset,
                "text": seg["text"].strip(),
            }
            for seg in segments
            if seg.get("text", "").strip()
        ]

    # Fallback: no timestamps — return whole text as single segment
    text = result.get("text", "").strip()
    if text:
        logger.warning(f"STT returned no segments with timestamps, using full text as single segment. Raw response: {result}")
        from backend.services.processor import get_duration
        try:
            duration = get_duration(audio_path)
        except Exception:
            duration = 0.0
        return [{"start": time_offset, "end": time_offset + duration, "text": text}]

    return []
