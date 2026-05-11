"""
Retry utility with exponential backoff for HTTP API calls.
"""
import time
import logging
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

MAX_RETRIES = 5
BASE_DELAY = 1.0  # seconds


def retry_call(fn: Callable[[], T], max_retries: int = MAX_RETRIES, base_delay: float = BASE_DELAY) -> T:
    """Call fn with exponential backoff retry.

    On failure sleeps: base_delay * 2^attempt (1s, 2s, 4s, 8s, 16s).
    """
    last_exc = None
    for attempt in range(max_retries + 1):  # 1 initial + N retries
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
    raise last_exc
