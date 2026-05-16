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
    http_proxy: Optional[str] = None,
    https_proxy: Optional[str] = None,
) -> dict:
    """
    Send an audio file to a Telegram chat.
    Returns the Telegram API response dict.
    """
    from backend.services.proxy import build_proxies

    url = f"{TELEGRAM_API}/bot{bot_token}/sendAudio"

    with open(audio_path, "rb") as f:
        files = {"audio": (os.path.basename(audio_path), f, "audio/mpeg")}
        data = {
            "chat_id": chat_id,
            "caption": caption[:1024],  # Telegram caption limit
            "parse_mode": "HTML",
        }
        if title:
            data["title"] = title[:64]

        proxies = build_proxies(http_proxy, https_proxy)
        logger.info(f"Sending audio to Telegram chat {chat_id}" + (f" via proxy {proxies}" if proxies else ""))
        client_kwargs = {"proxies": proxies} if proxies else {}
        with httpx.Client(**client_kwargs) as client:
            response = client.post(url, data=data, files=files, timeout=120)

    if response.status_code != 200:
        raise RuntimeError(f"Telegram API error {response.status_code}: {response.text}")

    result = response.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API returned error: {result.get('description')}")

    return result


def check_connection(
    bot_token: str,
    http_proxy: Optional[str] = None,
    https_proxy: Optional[str] = None,
) -> bool:
    """Verify bot token by calling getMe."""
    from backend.services.proxy import build_proxies

    try:
        url = f"{TELEGRAM_API}/bot{bot_token}/getMe"
        proxies = build_proxies(http_proxy, https_proxy)
        client_kwargs = {"proxies": proxies} if proxies else {}
        with httpx.Client(**client_kwargs) as client:
            response = client.get(url, timeout=10)
        return response.status_code == 200 and response.json().get("ok", False)
    except Exception:
        return False
