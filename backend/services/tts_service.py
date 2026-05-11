"""
TTS service using wangwangit/tts worker.
Endpoint: POST /v1/audio/speech
Used for article/text materials that have no original audio.
"""
import httpx
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

import random

DEFAULT_VOICE = "en-US-AvaMultilingualNeural"

# Curated high-quality neural voices from Microsoft Edge TTS
# These are considered more natural and less "scripted" than standard voices.
VOICES = {
    "en": [
        "en-US-AvaMultilingualNeural",
        "en-US-AndrewMultilingualNeural",
        "en-US-EmmaMultilingualNeural",
        "en-US-BrianMultilingualNeural",
        "en-US-AvaNeural",
        "en-US-AndrewNeural",
        "en-US-AriaNeural",
        "en-US-SteffanNeural",
        "en-GB-SoniaNeural",
        "en-GB-RyanNeural",
    ],
    "zh": [
        "zh-CN-XiaoxiaoMultilingualNeural",
        "zh-CN-YunyiMultilingualNeural",
        "zh-CN-XiaoxiaoNeural",
        "zh-CN-YunxiNeural",
        "zh-CN-XiaoyiNeural",
        "zh-CN-YunjianNeural",
        "zh-CN-XiaomengNeural",
    ]
}


def get_random_voice(lang: str = "en") -> str:
    """Pick a random voice for the given language prefix (e.g. 'en', 'zh')."""
    # Normalize language code (e.g. 'en-US' -> 'en')
    lang_prefix = lang.split('-')[0].lower()
    voice_list = VOICES.get(lang_prefix, VOICES["en"])
    return random.choice(voice_list)



def synthesize(
    text: str,
    output_path: str,
    worker_url: str,
    voice: str = DEFAULT_VOICE,
    speed: float = 1.0,
) -> str:
    """
    Convert text to speech and save as mp3.
    Returns the output_path.
    """
    url = f"{worker_url.rstrip('/')}/v1/audio/speech"

    payload = {
        "input": text,
        "voice": voice,
        "speed": speed,
        "pitch": "0",
        "style": "general",
    }

    logger.info(f"Calling TTS API for {len(text)} chars: {url}")
    from backend.services.retry import retry_call
    response = retry_call(lambda: httpx.post(url, json=payload, timeout=120))

    if response.status_code != 200:
        raise RuntimeError(f"TTS API error {response.status_code}: {response.text}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(response.content)

    logger.info(f"TTS audio saved: {output_path}")
    return output_path
