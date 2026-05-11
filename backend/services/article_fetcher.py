"""
Article fetcher: given a URL, extracts the main article text using httpx + BeautifulSoup4.
"""
import httpx
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Tags whose text we consider article body
CONTENT_TAGS = ["article", "main", "section", "div"]
BLOCK_TAGS = ["p", "h1", "h2", "h3", "h4", "li"]


def fetch(url: str) -> str:
    """
    Fetch a webpage and extract the main readable text.
    Returns plain text (paragraphs joined by newlines).
    """
    logger.info(f"Fetching article: {url}")
    from backend.services.retry import retry_call

    def _do_request():
        resp = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=30)
        resp.raise_for_status()
        return resp

    response = retry_call(_do_request)

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove scripts, styles, ads
    for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
        tag.decompose()

    # Try to find the most likely article container
    article = soup.find("article") or soup.find("main") or soup.body

    if not article:
        raise RuntimeError("Could not extract article content from page")

    # Collect text blocks
    paragraphs = []
    for tag in article.find_all(BLOCK_TAGS):
        text = tag.get_text(separator=" ", strip=True)
        if len(text) > 20:  # Skip tiny fragments
            paragraphs.append(text)

    if not paragraphs:
        # Fallback: all text
        paragraphs = [article.get_text(separator="\n", strip=True)]

    result = "\n".join(paragraphs)
    logger.info(f"Extracted {len(result)} chars from {url}")
    return result
