"""
Telegram Bot API integration (using raw HTTP, no external library needed).
Sends audio files with text captions to a Telegram chat.
"""
import httpx
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


def send_audio(
    bot_token: str,
    chat_id: str,
    audio_path: str,
    caption: str,
    title: Optional[str] = None,
) -> dict:
    """
    Send an audio file to a Telegram chat.
    Returns the Telegram API response dict.
    """
    url = f"{TELEGRAM_API}/bot{bot_token}/sendAudio"

    data = {
        "chat_id": chat_id,
        "caption": caption[:1024],  # Telegram caption limit
        "parse_mode": "HTML",
    }
    if title:
        data["title"] = title[:64]

    def _do_request():
        with open(audio_path, "rb") as f:
            files = {"audio": (os.path.basename(audio_path), f, "audio/mpeg")}
            resp = httpx.post(url, data=data, files=files, timeout=120)
        if resp.status_code != 200:
            raise RuntimeError(f"Telegram API error {resp.status_code}: {resp.text}")
        result = resp.json()
        if not result.get("ok"):
            raise RuntimeError(f"Telegram API returned error: {result.get('description')}")
        return result

    logger.info(f"Sending audio to Telegram chat {chat_id}")
    from backend.services.retry import retry_call
    response = retry_call(_do_request)

    return result


def check_connection(bot_token: str) -> bool:
    """Verify bot token by calling getMe."""
    try:
        url = f"{TELEGRAM_API}/bot{bot_token}/getMe"
        response = httpx.get(url, timeout=10)
        return response.status_code == 200 and response.json().get("ok", False)
    except Exception:
        return False
