"""Shared plumbing: CT time helpers, retry decorator, safe-fetch wrapper, HTTP session."""
import functools
import logging
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yaml

logger = logging.getLogger("morning_brief")

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "config.yml"

CT = ZoneInfo("America/Chicago")

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

session = requests.Session()
session.headers.update({"User-Agent": BROWSER_UA})


def now_ct() -> datetime:
    """Current tz-aware datetime in America/Chicago."""
    return datetime.now(CT)


def retry(times: int = 3, backoff: float = 2.0):
    """Retry a network call up to `times`, sleeping `backoff ** attempt` seconds between tries."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(times):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 - deliberately broad, see safe()
                    last_exc = exc
                    if attempt < times - 1:
                        time.sleep(backoff**attempt)
            raise last_exc

        return wrapper

    return decorator


_config_cache = None


def load_config() -> dict:
    """Load and cache config/config.yml."""
    global _config_cache
    if _config_cache is None:
        with open(CONFIG_PATH, "r") as f:
            _config_cache = yaml.safe_load(f)
    return _config_cache


def safe(fn, *args, **kwargs):
    """Run a fetcher, log the exception, return None on any failure so rendering continues."""
    try:
        return fn(*args, **kwargs)
    except Exception:  # noqa: BLE001 - graceful degradation is the whole point
        logger.exception("Fetcher %s failed; degrading to unavailable", getattr(fn, "__name__", fn))
        return None
