"""Earnings calendar fetcher: Nasdaq calendar API (primary), Finnhub (fallback).

Independently runnable: `python -m src.fetch_earnings` prints its JSON.
"""
import json
import logging
import os
import re

from src.util import load_config, now_ct, retry, session

logger = logging.getLogger("morning_brief")

CAP_SHOWN = 15


def _notable_symbols(cfg: dict) -> set:
    symbols = set(cfg["universe"])
    for group_syms in cfg["watchlist"].values():
        symbols.update(group_syms.keys())
    return symbols


def _parse_market_cap(raw) -> float:
    if not raw:
        return 0.0
    digits = re.sub(r"[^\d.]", "", str(raw))
    try:
        return float(digits) if digits else 0.0
    except ValueError:
        return 0.0


@retry(times=2, backoff=2.0)
def _fetch_nasdaq(date_str: str) -> list:
    resp = session.get(
        f"https://api.nasdaq.com/api/calendar/earnings?date={date_str}",
        headers={"Accept": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    rows = resp.json().get("data", {}).get("rows") or []
    out = []
    for r in rows:
        out.append(
            {
                "symbol": r.get("symbol"),
                "name": r.get("name") or r.get("companyName") or r.get("symbol"),
                "eps_est": r.get("epsForecast") or None,
                "time": r.get("time"),
                "market_cap": _parse_market_cap(r.get("marketCap")),
            }
        )
    return out


@retry(times=2, backoff=2.0)
def _fetch_finnhub(date_str: str) -> list:
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        return []
    resp = session.get(
        "https://finnhub.io/api/v1/calendar/earnings",
        params={"from": date_str, "to": date_str, "token": api_key},
        timeout=15,
    )
    resp.raise_for_status()
    rows = resp.json().get("earningsCalendar") or []
    out = []
    for r in rows:
        hour = r.get("hour")
        time_field = "time-pre-market" if hour == "bmo" else ("time-after-hours" if hour == "amc" else "time-not-supplied")
        eps = r.get("epsEstimate")
        out.append(
            {
                "symbol": r.get("symbol"),
                "name": r.get("symbol"),
                "eps_est": f"${eps}" if eps is not None else None,
                "time": time_field,
                "market_cap": 0.0,
            }
        )
    return out


def _bucket(rows: list, notable: set) -> dict:
    before_open, after_close = [], []
    for r in rows:
        entry = {
            "symbol": r["symbol"],
            "name": r["name"],
            "eps_est": r["eps_est"],
            "notable": r["symbol"] in notable,
            "market_cap": r["market_cap"],
        }
        if r["time"] == "time-pre-market":
            before_open.append(entry)
        elif r["time"] == "time-after-hours":
            after_close.append(entry)

    def finalize(lst):
        lst.sort(key=lambda e: e["market_cap"], reverse=True)
        shown = lst[:CAP_SHOWN]
        overflow = max(0, len(lst) - CAP_SHOWN)
        for e in shown:
            del e["market_cap"]
        return {"shown": shown, "overflow_count": overflow}

    return {"before_open": finalize(before_open), "after_close": finalize(after_close)}


def fetch_earnings(cfg: dict = None) -> dict:
    cfg = cfg or load_config()
    date_str = now_ct().strftime("%Y-%m-%d")
    notable = _notable_symbols(cfg)

    rows = []
    source = None
    try:
        rows = _fetch_nasdaq(date_str)
        if rows:
            source = "nasdaq"
    except Exception:
        logger.exception("Nasdaq earnings fetch failed")

    if not rows:
        try:
            rows = _fetch_finnhub(date_str)
            if rows:
                source = "finnhub"
        except Exception:
            logger.exception("Finnhub earnings fetch failed")

    result = _bucket(rows, notable)
    result["fetched_at"] = now_ct().isoformat()
    result["source"] = source
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(fetch_earnings(), indent=2, default=str))
