"""
STT transcription service.
Supports two backends:
  - "api": remote wangwangit/tts worker (SiliconFlow FunAudioLLM/SenseVoiceSmall)
  - "whisper_cpp": local whisper.cpp via whisper_cpp_python

Handles large files by chunking them first.
"""
import httpx
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Max file size before chunking (bytes) — worker limit is 10MB
MAX_FILE_SIZE = 9 * 1024 * 1024  # 9MB safety margin

# Shared whisper model instance (lazy-loaded, reused across calls)
_whisper_model = None
_whisper_model_path = None

# ── Whisper model download ──────────────────────────────────

WHISPER_MODEL_SIZES = {
    "tiny": "ggml-tiny.bin",
    "base": "ggml-base.bin",
    "small": "ggml-small.bin",
    "medium": "ggml-medium.bin",
    "large": "ggml-large-v3.bin",
}
WHISPER_MODEL_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"

# Approximate sizes for display
WHISPER_MODEL_SIZE_MB = {
    "tiny": 78,
    "base": 148,
    "small": 488,
    "medium": 1530,
    "large": 3100,
}


def download_whisper_model(model_size: str = "base", save_dir: str = "") -> str:
    """
    Download a whisper GGML model from HuggingFace.
    Returns the absolute path to the saved model file.
    """
    if model_size not in WHISPER_MODEL_SIZES:
        raise ValueError(f"Unknown model size: {model_size}. Choose from: {list(WHISPER_MODEL_SIZES.keys())}")

    filename = WHISPER_MODEL_SIZES[model_size]
    url = f"{WHISPER_MODEL_BASE_URL}/{filename}"

    if not save_dir:
        from backend.config import settings
        save_dir = os.path.join(settings.STORAGE_BASE_PATH, "models")
    os.makedirs(save_dir, exist_ok=True)

    save_path = os.path.join(save_dir, filename)

    if os.path.exists(save_path):
        logger.info(f"Model already exists at {save_path}")
        return save_path

    approx_mb = WHISPER_MODEL_SIZE_MB.get(model_size, "?")
    logger.info(f"Downloading whisper model '{model_size}' ({approx_mb} MB) from {url}")
    logger.info(f"Saving to {save_path}")

    with httpx.stream("GET", url, timeout=1200, follow_redirects=True) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(save_path, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
        if total:
            logger.info(f"Model downloaded: {downloaded}/{total} bytes ({downloaded * 100 // total}%)")

    global _whisper_model, _whisper_model_path
    _whisper_model = None
    _whisper_model_path = None

    logger.info(f"Model saved to {save_path}")
    return save_path


def transcribe(
    wav_path: str,
    worker_url: str,
    token: Optional[str] = None,
    chunk_dir: Optional[str] = None,
    http_proxy: Optional[str] = None,
    https_proxy: Optional[str] = None,
    backend: str = "api",
    whisper_model_path: str = "",
) -> list[dict]:
    """
    Transcribe an audio file. Returns list of segments:
    [{"start": float, "end": float, "text": str}, ...]

    If the file is too large, splits into chunks first and offsets timestamps.
    """
    if backend == "whisper_cpp":
        return _transcribe_whisper_cpp(wav_path, model_path=whisper_model_path)

    # API backend — may chunk large files
    file_size = os.path.getsize(wav_path)

    if file_size <= MAX_FILE_SIZE:
        return _transcribe_api(wav_path, worker_url, token, time_offset=0.0,
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
            segs = _transcribe_api(chunk_path, worker_url, token, time_offset=time_offset,
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


def _transcribe_api(
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

    proxies = build_proxies(http_proxy, https_proxy)

    logger.info(f"Calling STT API: {url}" + (f" via proxy {proxies}" if proxies else ""))

    def _do_request():
        with open(audio_path, "rb") as f:
            files = {"file": (os.path.basename(audio_path), f, "audio/wav")}
            data = {"response_format": "verbose_json"}
            if token:
                data["token"] = token
            client_kwargs = {"proxies": proxies} if proxies else {}
            with httpx.Client(**client_kwargs) as client:
                resp = client.post(url, files=files, data=data, timeout=300)
        if resp.status_code != 200:
            raise RuntimeError(f"STT API error {resp.status_code}: {resp.text}")
        return resp

    from backend.services.retry import retry_call
    response = retry_call(_do_request)

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


def _check_whisper_installed() -> bool:
    """Check if whisper_cpp_python package is installed and its shared library is loadable."""
    try:
        from whisper_cpp_python import Whisper  # noqa: F401
        return True
    except (ImportError, FileNotFoundError, OSError, RuntimeError, AttributeError) as e:
        logger.warning(f"whisper_cpp_python is not ready: {e}")
        return False


def _transcribe_whisper_cpp(
    wav_path: str,
    model_path: str = "",
) -> list[dict]:
    """Transcribe using local whisper.cpp via whisper_cpp_python."""
    global _whisper_model, _whisper_model_path

    try:
        from whisper_cpp_python import Whisper
    except ImportError:
        raise RuntimeError(
            "whisper_cpp_python is not installed. "
            "Install it with: uv pip install whisper-cpp-python"
        )

    resolved_path = model_path or "ggml-base.bin"

    if _whisper_model is None or _whisper_model_path != resolved_path:
        logger.info(f"Loading whisper model: {resolved_path}")
        _whisper_model = Whisper(
            model_path=resolved_path,
            n_threads=1 
        )
        _whisper_model_path = resolved_path

    result = _whisper_model.transcribe(wav_path)
    segments = []
    for seg in result.get("segments", []):
        text = seg.get("text", "").strip()
        if text:
            segments.append({
                "start": seg.get("t0", 0) / 100.0,
                "end": seg.get("t1", 0) / 100.0,
                "text": text,
            })

    if not segments:
        text = result.get("text", "").strip()
        if text:
            from backend.services.processor import get_duration
            try:
                duration = get_duration(wav_path)
            except Exception:
                duration = 0.0
            segments = [{"start": 0.0, "end": duration, "text": text}]

    return segments
