"""
Shared proxy helper: builds an httpx-compatible proxies dict from per-user
or global settings.  All HTTP-calling services import `build_proxies` from here
so behaviour stays consistent.
"""
from typing import Optional


def build_proxies(
    http_proxy: Optional[str] = None,
    https_proxy: Optional[str] = None,
) -> dict[str, str]:
    """
    Return an httpx proxies dict (mapping scheme → proxy URL).

    Priority:
      1. Explicit arguments (per-user settings).
      2. Global settings from config.py (.env / env vars).
    """
    from backend.config import settings

    http = http_proxy or settings.HTTP_PROXY or None
    https = https_proxy or settings.HTTPS_PROXY or settings.HTTP_PROXY or None

    proxies: dict[str, str] = {}
    if http:
        proxies["http://"] = http
    if https:
        proxies["https://"] = https
    return proxies
