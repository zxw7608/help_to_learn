"""
Voice Activity Detection service using Silero VAD (ONNX backend).
Detects speech segments from WAV audio for smarter cutting before STT.

Reads WAV via stdlib ``wave`` + ``numpy`` to avoid torchaudio's torchcodec
requirement (torchaudio >= 2.9 needs an extra install). The numpy array is
wrapped as a torch Tensor for the silero_vad post-processing utilities.
"""
import logging
import wave

import numpy as np
import torch

from silero_vad import load_silero_vad, get_speech_timestamps

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        logger.info("Loading Silero VAD model (ONNX)...")
        _model = load_silero_vad(onnx=True)
        logger.info("Silero VAD model loaded")
    return _model


def _read_wav(wav_path: str) -> np.ndarray:
    """
    Read a 16-bit mono PCM WAV and return float32 samples in [-1, 1].
    Uses stdlib ``wave`` — avoids torchaudio / torchcodec.
    """
    with wave.open(wav_path, "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        nframes = wf.getnframes()
        data = wf.readframes(nframes)

    if sampwidth == 2:
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 1:
        samples = (np.frombuffer(data, dtype=np.uint8).astype(np.float32) - 128) / 128.0
    elif sampwidth == 4:
        samples = np.frombuffer(data, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth}")

    # Free the raw bytes immediately — no longer needed after conversion
    del data

    if nchannels > 1:
        # mean() returns float64; cast once and return directly (avoid extra copy)
        return samples.reshape(-1, nchannels).mean(axis=1).astype(np.float32)

    # samples is already float32 — return as-is, no redundant copy
    return samples


def detect_speech_segments(
    wav_path: str,
    min_speech_duration_ms: int = 500,
    min_silence_duration_ms: int = 400,
    threshold: float = 0.5,
    merge_gap: float = 1.5,
    max_duration: float = 15.0,
) -> list[dict]:
    """
    Detect speech segments in a 16kHz mono WAV file.

    Returns list of {"start": float, "end": float} in seconds.
    Returns empty list if no speech is detected.
    """
    model = _get_model()
    audio_np = _read_wav(wav_path)
    audio_tensor = torch.from_numpy(audio_np)

    raw = get_speech_timestamps(
        audio_tensor,
        model,
        threshold=threshold,
        min_speech_duration_ms=min_speech_duration_ms,
        min_silence_duration_ms=min_silence_duration_ms,
        return_seconds=True,
    )

    # Release the audio arrays immediately — VAD is done, no need to hold ~73MB
    del audio_tensor, audio_np

    if not raw:
        logger.warning("VAD detected no speech segments")
        return []

    merged = _merge_segments(raw, merge_gap, max_duration)
    logger.info(
        "VAD detected %d raw speech segments, merged to %d (gap=%.1fs, max_dur=%.1fs)",
        len(raw), len(merged), merge_gap, max_duration,
    )
    return merged


def _merge_segments(
    segments: list[dict],
    gap_threshold: float,
    max_duration: float,
) -> list[dict]:
    """Merge adjacent VAD segments whose gap is below the threshold."""
    if not segments:
        return []
    merged = [dict(segments[0])]
    for seg in segments[1:]:
        prev = merged[-1]
        gap = seg["start"] - prev["end"]
        if gap < gap_threshold and (seg["end"] - prev["start"]) <= max_duration:
            prev["end"] = seg["end"]
        else:
            merged.append(dict(seg))
    return merged
