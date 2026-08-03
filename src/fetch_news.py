"""Headlines fetcher (RSS via feedparser): pulls configured feeds, dedupes, caps output.

Independently runnable: `python -m src.fetch_news` prints its JSON.
"""
import calendar
import json
import logging
import re
from collections import OrderedDict, deque
from datetime import datetime, timedelta, timezone

import feedparser

from src.util import CT, load_config, now_ct, retry, session

logger = logging.getLogger("morning_brief")


def _normalize_words(title: str) -> list:
    t = title.lower()
    t = re.sub(r"[^\w\s]", "", t)
    return t.split()


def _shares_leading_words(a: list, b: list, threshold: int = 8) -> bool:
    shared = 0
    for wa, wb in zip(a, b):
        if wa == wb:
            shared += 1
        else:
            break
    return shared >= threshold


@retry(times=2, backoff=1.5)
def _parse_feed(url: str):
    # Fetch through the shared session (browser UA, explicit timeout) instead of letting
    # feedparser.parse(url) do its own HTTP fetch -- feedparser's default fetch has no
    # timeout and a non-browser UA, and at least one feed source hangs indefinitely under
    # those conditions (confirmed: plain requests with a timeout succeeds against the same
    # URL in under a second). A hang here, unlike a clean failure, isn't caught by retry/
    # exception handling and could eat the whole build.
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        raise parsed.bozo_exception or RuntimeError(f"Failed to parse feed: {url}")
    return parsed


def fetch_news(cfg: dict = None) -> dict:
    cfg = cfg or load_config()
    window = timedelta(hours=cfg["headline_window_hours"])
    cutoff = now_ct() - window

    candidates = []
    for feed_cfg in cfg["rss_feeds"]:
        try:
            parsed = _parse_feed(feed_cfg["url"])
        except Exception:
            logger.exception("RSS feed failed: %s", feed_cfg["name"])
            continue
        for entry in parsed.entries:
            struct = entry.get("published_parsed") or entry.get("updated_parsed")
            if not struct:
                continue
            published = datetime.fromtimestamp(calendar.timegm(struct), tz=timezone.utc).astimezone(CT)
            if published < cutoff:
                continue
            title = entry.get("title", "").strip()
            if not title:
                continue
            candidates.append(
                {
                    "title": title,
                    "source": feed_cfg["name"],
                    "url": entry.get("link", ""),
                    "published_ct": published.isoformat(),
                    "_sort": published,
                }
            )

    candidates.sort(key=lambda c: c["_sort"], reverse=True)
    kept = _pick_diverse(candidates, cfg["max_headlines"])
    kept.sort(key=lambda c: c["_sort"], reverse=True)

    for c in kept:
        del c["_sort"]

    return {"fetched_at": now_ct().isoformat(), "headlines": kept}


def _pick_diverse(candidates: list, max_headlines: int) -> list:
    """Round-robin across sources (newest-first within each) instead of a flat recency
    sort, so a single prolific source can't crowd out the rest of a diversified feed
    list. Near-duplicate titles are still skipped globally, same threshold as before."""
    by_source = OrderedDict()
    for c in candidates:
        by_source.setdefault(c["source"], deque()).append(c)

    kept = []
    kept_words = []
    active_sources = list(by_source.keys())
    while active_sources and len(kept) < max_headlines:
        for source in list(active_sources):
            queue = by_source[source]
            picked = None
            while queue:
                candidate = queue.popleft()
                words = _normalize_words(candidate["title"])
                if any(_shares_leading_words(words, kw) for kw in kept_words):
                    continue
                picked = candidate
                break
            if picked:
                kept.append(picked)
                kept_words.append(_normalize_words(picked["title"]))
                if len(kept) >= max_headlines:
                    break
            if not queue:
                active_sources.remove(source)

    return kept


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(fetch_news(), indent=2, default=str))
