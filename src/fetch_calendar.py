"""Economic calendar fetcher (ForexFactory weekly JSON feed).

Independently runnable: `python -m src.fetch_calendar` prints its JSON.
"""
import json
import logging
import re
from collections import OrderedDict
from datetime import datetime

from src.util import CT, load_config, now_ct, retry, session

logger = logging.getLogger("morning_brief")

FED_RE = re.compile(r"Fed|FOMC|Powell", re.IGNORECASE)


@retry(times=3, backoff=2.0)
def _fetch_feed(url: str) -> list:
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _qualifying_events(raw: list) -> list:
    """USD events that are High/Medium impact, or any Fed/FOMC/Powell item regardless of impact."""
    out = []
    for item in raw:
        try:
            dt = datetime.fromisoformat(item["date"]).astimezone(CT)
        except (KeyError, ValueError):
            continue
        if item.get("country") != "USD":
            continue

        is_fed = bool(FED_RE.search(item.get("title", "")))
        impact = item.get("impact", "")
        if impact not in ("High", "Medium") and not is_fed:
            continue

        out.append(
            {
                "dt": dt,
                "time_ct": dt.strftime("%-I:%M %p CT"),
                "title": item.get("title", ""),
                "impact": impact,
                "forecast": item.get("forecast") or None,
                "previous": item.get("previous") or None,
                "actual": item.get("actual") or None,
                "is_fed": is_fed,
            }
        )
    out.sort(key=lambda e: e["dt"])
    return out


def fetch_calendar(cfg: dict = None) -> dict:
    cfg = cfg or load_config()
    raw = _fetch_feed(cfg["economic_calendar_url"])
    qualifying = _qualifying_events(raw)

    today_ct = now_ct().date()
    events = []
    week = OrderedDict()

    for e in qualifying:
        date = e["dt"].date()
        row = {k: v for k, v in e.items() if k != "dt"}
        if date == today_ct:
            events.append(row)
        elif date > today_ct:
            key = date.isoformat()
            if key not in week:
                week[key] = {"weekday": e["dt"].strftime("%A"), "date_label": e["dt"].strftime("%b %-d"), "events": []}
            week[key]["events"].append(row)

    return {
        "fetched_at": now_ct().isoformat(),
        "events": events,
        "week": list(week.values()),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(fetch_calendar(), indent=2, default=str))
