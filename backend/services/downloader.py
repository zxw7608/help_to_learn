"""
yt-dlp downloader service.
Requires yt-dlp to be installed and available in PATH:
  pip install yt-dlp   OR   install system-wide / in container

Features:
- Proxy support via settings.YTDLP_PROXY (falls back to settings.HTTP_PROXY)
- Cookies support: uses settings.YTDLP_COOKIES path, or auto-detects ./cookies.txt
- Two-pass subtitle strategy:
    Pass 1: --list-subs --skip-download  → discover available languages
    Pass 2: --write-subs --sub-langs <best_lang>  → download only that language
- Falls back to STT when no subtitles are available.
- Encoding-safe: all subprocess I/O is bytes-mode decoded as utf-8.

Subtitle parsing is delegated to backend.services.subtitle_parser.
"""
import os
import subprocess
import logging
from typing import Optional

from backend.services.subtitle_parser import (
    parse_sub_file,
    merge_nearby_segments,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Subprocess helper — encoding-safe on all platforms (incl. Windows)
# ─────────────────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 600) -> tuple[int, str, str]:
    """
    Run a command and return (returncode, stdout, stderr).
    Uses bytes mode + explicit utf-8 decode to avoid Windows cp936/gbk issues.
    --no-colors keeps yt-dlp output clean (no ANSI escapes in logs).
    """
    full_cmd = cmd + ["--no-colors"] if "yt-dlp" in cmd[0] else cmd
    logger.debug(f"Exec: {' '.join(full_cmd)}")
    proc = subprocess.run(
        full_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = proc.stderr.decode("utf-8", errors="replace")
    return proc.returncode, stdout, stderr


# ─────────────────────────────────────────────────────────────────
# Proxy / Cookies helpers
# ─────────────────────────────────────────────────────────────────

def _proxy_args(
    http_proxy: Optional[str] = None,
    ytdlp_proxy: Optional[str] = None,
) -> list[str]:
    from backend.config import settings
    proxy = ytdlp_proxy or http_proxy or settings.YTDLP_PROXY or settings.HTTP_PROXY or None
    return ["--proxy", proxy] if proxy else []


def _cookies_args(ytdlp_cookies: Optional[str] = None) -> list[str]:
    """
    Resolve cookies.txt path:
      1. Explicit per-user ytdlp_cookies
      2. settings.YTDLP_COOKIES  (env var / .env)
      3. ./cookies.txt           (project root, auto-detected)
    """
    from backend.config import settings

    cookie_path = ytdlp_cookies or settings.YTDLP_COOKIES or None
    if cookie_path:
        path = os.path.abspath(cookie_path)
        if os.path.isfile(path):
            logger.info(f"yt-dlp: using cookies from config: {path}")
            return ["--cookies", path]
        logger.warning(f"yt-dlp: YTDLP_COOKIES path not found: {path}")

    auto = os.path.abspath("cookies.txt")
    if os.path.isfile(auto):
        logger.info(f"yt-dlp: auto-detected cookies.txt: {auto}")
        return ["--cookies", auto]

    return []


def _common_args(
    http_proxy: Optional[str] = None,
    ytdlp_proxy: Optional[str] = None,
    ytdlp_cookies: Optional[str] = None,
) -> list[str]:
    """Args shared by every yt-dlp invocation."""
    return [*_proxy_args(http_proxy, ytdlp_proxy), *_cookies_args(ytdlp_cookies), "--no-playlist"]


# ─────────────────────────────────────────────────────────────────
# Subtitle language discovery (pass 1)
# ─────────────────────────────────────────────────────────────────

# Preferred subtitle languages, checked in order.
# Manual subs are tried first (prefix ""), auto-generated subs use "auto:" prefix.
_PREF_LANGS = ["en"]

# Subtitle language codes that are NOT real subtitles (e.g., Bilibili danmaku overlay)
_SUB_LANG_BLOCKLIST = {"danmaku", "live_chat"}

# Languages to never select, even as a fallback.
# Matched by segment: "zh" blocks zh, zh-Hans, zh-Hant, ai-zh, etc.
# (splits on "-" and checks each part, so "ai-zh" is also caught)
_SUB_LANG_DENYLIST = {"zh"}

def _list_available_subs(
    url: str,
    http_proxy: Optional[str] = None,
    ytdlp_proxy: Optional[str] = None,
    ytdlp_cookies: Optional[str] = None,
) -> dict[str, list[str]]:
    """
    Run `yt-dlp --list-subs --skip-download` and parse the output.

    Returns a dict:
      {
        "manual": ["en", "zh-Hans", ...],   # manually uploaded subs
        "auto":   ["en", "zh-Hans", ...],   # auto-generated subs
      }
    """
    cmd = [
        "yt-dlp",
        "--list-subs",
        "--skip-download",
        *_common_args(http_proxy, ytdlp_proxy, ytdlp_cookies),
        url,
    ]
    rc, stdout, stderr = _run(cmd, timeout=60)
    if rc != 0:
        logger.warning(f"yt-dlp --list-subs failed (rc={rc}): {stderr[:500]}")
        return {"manual": [], "auto": []}

    manual: list[str] = []
    auto: list[str] = []

    # yt-dlp output sections look like:
    #   [info] Available subtitles for <id>:
    #   Language  Name  Formats
    #   en        English  vtt, ttml
    #   zh-Hans   Chinese  vtt
    #
    #   [info] Available automatic captions for <id>:
    #   Language  Name  Formats
    #   en        English  vtt
    in_manual = False
    in_auto = False

    for line in stdout.splitlines():
        low = line.lower()
        if "available subtitles" in low:
            in_manual = True
            in_auto = False
            continue
        if "available automatic captions" in low or "auto-generated" in low:
            in_auto = True
            in_manual = False
            continue
        # Skip header and blank lines
        if not line.strip() or line.strip().lower().startswith("language"):
            continue
        # Each subtitle line starts with the language code
        parts = line.split()
        if parts:
            lang = parts[0]
            if in_manual:
                manual.append(lang)
            elif in_auto:
                auto.append(lang)

    manual = [l for l in manual if l not in _SUB_LANG_BLOCKLIST]
    auto = [l for l in auto if l not in _SUB_LANG_BLOCKLIST]
    logger.info(f"Available manual subs: {manual}")
    logger.info(f"Available auto-generated subs: {auto}")
    return {"manual": manual, "auto": auto}


def _pick_best_lang(available: dict[str, list[str]]) -> tuple[Optional[str], bool]:
    """
    Pick the best subtitle language from the available lists.

    Returns (lang_code, is_auto):
      lang_code — the yt-dlp language code to request, or None
      is_auto   — True if this is an auto-generated caption
    """
    # Prefer manual subs
    for lang in _PREF_LANGS:
        for avail in available["manual"]:
            if avail == lang or avail.startswith(lang):
                return avail, False

    # Fall back to auto-generated
    for lang in _PREF_LANGS:
        for avail in available["auto"]:
            if avail == lang or avail.startswith(lang):
                return avail, True

    def _is_denied(lang: str) -> bool:
        parts = lang.lower().replace("_", "-").split("-")
        return bool(_SUB_LANG_DENYLIST & set(parts))

    # Accept any manual sub that isn't denied
    for lang in available["manual"]:
        if not _is_denied(lang):
            return lang, False

    # Accept any auto sub that isn't denied
    for lang in available["auto"]:
        if not _is_denied(lang):
            return lang, True

    return None, False




# ─────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────

def download(
    url: str,
    material_id: int,
    user_id: int,
    base_path: str,
    http_proxy: Optional[str] = None,
    ytdlp_proxy: Optional[str] = None,
    ytdlp_cookies: Optional[str] = None,
) -> tuple[str, list[dict]]:
    """
    Download video/audio from URL using yt-dlp (two-pass subtitle strategy).

    Pass 1 — list available subtitle languages (--list-subs --skip-download).
    Pass 2 — download video + the best available subtitle language.
             If no subtitles exist, downloads video only (caller uses STT).

    Proxy/cookies args override per-user settings; fall back to global config.

    Returns:
        (file_path, subtitle_segments)

        - file_path         : absolute path to the downloaded video/audio file
        - subtitle_segments : [{start, end, text}, ...] in seconds.
                              Empty list → caller should fall back to STT.
    """
    out_dir = os.path.join(base_path, "originals", str(user_id), str(material_id))
    os.makedirs(out_dir, exist_ok=True)

    output_template = os.path.join(out_dir, "video.%(ext)s")
    common = _common_args(http_proxy, ytdlp_proxy, ytdlp_cookies)

    # ── Pass 1: Discover available subtitle languages ─────────────────────────
    logger.info(f"Checking available subtitles for: {url}")
    available = _list_available_subs(url, http_proxy, ytdlp_proxy, ytdlp_cookies)
    best_lang, is_auto = _pick_best_lang(available)

    if best_lang:
        logger.info(
            f"Selected subtitle lang='{best_lang}' "
            f"({'auto-generated' if is_auto else 'manual'})"
        )
    else:
        logger.info("No subtitles found — will download video only (STT fallback)")

    # ── Pass 2: Download video (+ subtitle if available) ─────────────────────
    sub_args: list[str] = []
    if best_lang:
        if is_auto:
            sub_args = ["--write-auto-sub", "--sub-langs", best_lang]
        else:
            sub_args = ["--write-subs", "--sub-langs", best_lang]
        # Convert to VTT for uniform parsing; SRT as fallback
        sub_args += ["--sub-format", "vtt/srt/best", "--convert-subs", "vtt"]

    cmd = [
        "yt-dlp",
        "-o", output_template,
        "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        *sub_args,
        *common,
        url,
    ]
    logger.info(f"Downloading: {' '.join(cmd)}")
    rc, stdout, stderr = _run(cmd, timeout=600)

    if rc != 0:
        raise RuntimeError(f"yt-dlp download failed:\n{stderr}")

    # ── Locate the downloaded video file ─────────────────────────────────────
    all_files = [f for f in os.listdir(out_dir) if os.path.isfile(os.path.join(out_dir, f))]
    video_files = [f for f in all_files if f.lower().endswith(".mp4")]
    if not video_files:
        video_files = [f for f in all_files if not f.endswith((".vtt", ".srt", ".json", ".ass"))]
    if not video_files:
        raise RuntimeError("yt-dlp did not produce any output file")

    video_path = os.path.join(out_dir, sorted(video_files)[0])
    logger.info(f"Downloaded video: {video_path}")

    # ── Find and parse subtitle file ─────────────────────────────────────────
    sub_files = [f for f in all_files if f.endswith((".vtt", ".srt"))]
    subtitle_segments: list[dict] = []

    if sub_files:
        # If we requested a specific lang, prefer files that contain it
        chosen = None
        if best_lang:
            for sf in sub_files:
                if best_lang.lower() in sf.lower():
                    chosen = sf
                    break
        chosen = chosen or sub_files[0]

        sub_path = os.path.join(out_dir, chosen)
        logger.info(f"Parsing subtitle file: {chosen}")
        try:
            segs = parse_sub_file(sub_path)
            segs = merge_nearby_segments(segs)
            logger.info(f"Parsed {len(segs)} subtitle segments")
            subtitle_segments = segs
        except Exception as exc:
            logger.warning(f"Subtitle parse error ({chosen}): {exc} — falling back to STT")
            subtitle_segments = []
    else:
        logger.info("No subtitle file produced — caller should use STT")

    return video_path, subtitle_segments
