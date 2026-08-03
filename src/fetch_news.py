"""Headlines fetcher (RSS via feedparser): pulls configured feeds, dedupes, caps output.

Independently runnable: `python -m src.fetch_news` prints its JSON.
"""
import calendar
import json
import logging
import re
from datetime import datetime, timedelta, timezone

import feedparser

from src.util import CT, load_config, now_ct, retry

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
    parsed = feedparser.parse(url)
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

    kept = []
    kept_words = []
    for c in candidates:
        words = _normalize_words(c["title"])
        if any(_shares_leading_words(words, kw) for kw in kept_words):
            continue
        kept.append(c)
        kept_words.append(words)
        if len(kept) >= cfg["max_headlines"]:
            break

    for c in kept:
        del c["_sort"]

    return {"fetched_at": now_ct().isoformat(), "headlines": kept}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(fetch_news(), indent=2, default=str))
