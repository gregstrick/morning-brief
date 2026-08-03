"""Deterministic morning digest: computes the "This Morning" card straight from the
already-fetched market/calendar/earnings/news data, no AI call and no API key.

Produces the same {headline, overnight, today_setup, risk_watch, watchlist_note} shape
the old AI synthesis used, so the template needed no restructuring -- just a different,
free, zero-signup way of filling it in.
"""
import logging

logger = logging.getLogger("morning_brief")


def _cap_first(s):
    """Capitalize only the first character -- str.capitalize() also lowercases the
    rest of the string, which mangles tickers and proper nouns (AAPL -> Aapl)."""
    return s[0].upper() + s[1:] if s else s


def _find(rows, symbol):
    for r in rows or []:
        if r.get("symbol") == symbol:
            return r
    return None


def _clean_name(name):
    """Strip a trailing "(closed)"/"(live)" session tag -- useful in tiles, awkward in prose."""
    for tag in (" (closed)", " (live)"):
        if name and name.lower().endswith(tag):
            return name[: -len(tag)]
    return name


def _pct(value, digits=1):
    return f"{value:+.{digits}f}%" if value is not None else None


def _fmt_list(items, conjunction="and"):
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} {conjunction} {items[1]}"
    return ", ".join(items[:-1]) + f", {conjunction} {items[-1]}"


def _build_headline(markets):
    futures = (markets or {}).get("futures") or []
    sp = _find(futures, "ES=F")
    nq = _find(futures, "NQ=F")

    if not sp or sp.get("change_pct") is None:
        return "Futures data unavailable this morning."

    change = sp["change_pct"]
    if abs(change) < 0.1:
        direction = "little changed"
    elif change > 0:
        direction = "pointing higher"
    else:
        direction = "pointing lower"

    detail = [f"S&P {_pct(change)}"]
    if nq and nq.get("change_pct") is not None:
        detail.append(f"Nasdaq {_pct(nq['change_pct'])}")

    headline = f"Futures {direction}: {', '.join(detail)}."

    vix = _find((markets or {}).get("volatility") or [], "^VIX")
    if vix and vix.get("change_pct") is not None and abs(vix["change_pct"]) >= 3:
        vdir = "up" if vix["change_pct"] >= 0 else "down"
        headline += f" VIX {vdir} {abs(vix['change_pct']):.1f}%."

    return headline


def _build_overnight(markets):
    markets = markets or {}
    parts = []

    intl = markets.get("international") or []
    movers = [r for r in intl if r.get("change_pct") is not None]
    if movers:
        biggest = max(movers, key=lambda r: abs(r["change_pct"]))
        if abs(biggest["change_pct"]) >= 0.5:
            direction = "up" if biggest["change_pct"] >= 0 else "down"
            parts.append(f"{_clean_name(biggest['name'])} leads overnight action, {direction} {abs(biggest['change_pct']):.1f}%")

    rates = markets.get("rates") or []
    tnx = _find(rates, "^TNX")
    if tnx and tnx.get("change_bp") is not None and abs(tnx["change_bp"]) >= 3:
        rdir = "up" if tnx["change_bp"] >= 0 else "down"
        parts.append(f"the 10-year yield is {rdir} {abs(tnx['change_bp']):.1f} bp to {tnx['yield_pct']:.2f}%")

    dcc = markets.get("dollar_commodities_crypto") or []
    for sym, label in (("CL=F", "WTI crude"), ("GC=F", "gold"), ("BTC-USD", "bitcoin")):
        row = _find(dcc, sym)
        if row and row.get("change_pct") is not None and abs(row["change_pct"]) >= 2:
            mdir = "up" if row["change_pct"] >= 0 else "down"
            parts.append(f"{label} is {mdir} {abs(row['change_pct']):.1f}%")

    if not parts:
        return "No standout overnight moves in international markets, rates, or commodities."
    return "Overnight: " + _fmt_list(parts) + "."


def _build_today_setup(calendar, earnings):
    parts = []
    events = (calendar or {}).get("events") if calendar else None

    if calendar is None:
        parts.append("economic calendar unavailable")
    elif events:
        fed_events = [e for e in events if e.get("is_fed")]
        high_events = [e for e in events if e.get("impact") == "High"]
        if high_events:
            e = high_events[0]
            parts.append(f"{e['title']} at {e['time_ct']} is today's highest-impact release")
        if fed_events:
            names = _fmt_list([e["title"] for e in fed_events[:2]])
            parts.append(f"Fed speakers on deck: {names}")
        if not high_events and not fed_events:
            parts.append(f"{len(events)} medium-impact US release(s) scheduled")
    else:
        parts.append("no high-impact US releases scheduled")

    earnings = earnings or {}
    before = (earnings.get("before_open") or {}).get("shown") or []
    after = (earnings.get("after_close") or {}).get("shown") or []
    notable = [e for e in (before + after) if e.get("notable")]
    if notable:
        names = _fmt_list([e["symbol"] for e in notable[:4]])
        parts.append(f"watchlist earnings today: {names}")
    elif before or after:
        parts.append(f"{len(before)} reporting before the open, {len(after)} after the close")

    if not parts:
        return "Nothing notable scheduled today."
    return "Today: " + _fmt_list(parts) + "."


def _build_risk_watch(markets, calendar):
    candidates = []
    markets = markets or {}

    events = (calendar or {}).get("events") if calendar else []
    fed_events = [e for e in (events or []) if e.get("is_fed")]
    high_events = [e for e in (events or []) if e.get("impact") == "High"]
    if fed_events:
        candidates.append(f"Fed commentary around {fed_events[0]['time_ct']} could move rates and equities together")
    elif high_events:
        candidates.append(f"{high_events[0]['title']} at {high_events[0]['time_ct']} is the day's main data risk")

    movers = markets.get("movers") or {}
    all_movers = (movers.get("gainers") or []) + (movers.get("losers") or [])
    extreme = [m for m in all_movers if m.get("premarket_pct") is not None and abs(m["premarket_pct"]) >= 5]
    if extreme:
        m = max(extreme, key=lambda x: abs(x["premarket_pct"]))
        mdir = "up" if m["premarket_pct"] >= 0 else "down"
        candidates.append(f"{m['symbol']} is {mdir} {abs(m['premarket_pct']):.1f}% pre-market, worth a look at why")

    if not candidates:
        return "Nothing flagged as an outsized risk to the session so far."
    return _cap_first(_fmt_list(candidates[:2])) + "."


def _build_watchlist_note(markets, earnings):
    markets = markets or {}
    watchlist = markets.get("watchlist") or {}
    watch_symbols = {r["symbol"] for rows in watchlist.values() for r in rows}

    moves = []
    for rows in watchlist.values():
        for r in rows:
            if r.get("session") == "pre" and r.get("premarket_pct") is not None and abs(r["premarket_pct"]) >= 2:
                moves.append(r)
    moves.sort(key=lambda r: abs(r["premarket_pct"]), reverse=True)

    earnings = earnings or {}
    before = (earnings.get("before_open") or {}).get("shown") or []
    after = (earnings.get("after_close") or {}).get("shown") or []
    watch_earnings = [e for e in (before + after) if e.get("symbol") in watch_symbols]

    parts = []
    if moves:
        m = moves[0]
        mdir = "up" if m["premarket_pct"] >= 0 else "down"
        parts.append(f"{m['symbol']} is {mdir} {abs(m['premarket_pct']):.1f}% pre-market")
    if watch_earnings:
        names = _fmt_list([e["symbol"] for e in watch_earnings[:3]])
        parts.append(f"{names} report{'s' if len(watch_earnings) == 1 else ''} today")

    if not parts:
        return "Nothing notable for the watchlist this morning."
    return _cap_first(_fmt_list(parts)) + "."


def build_digest(data: dict, early_close: bool = False) -> dict:
    markets = data.get("markets")
    calendar = data.get("calendar")
    earnings = data.get("earnings")

    return {
        "headline": _build_headline(markets),
        "overnight": _build_overnight(markets),
        "today_setup": _build_today_setup(calendar, earnings),
        "risk_watch": _build_risk_watch(markets, calendar),
        "watchlist_note": _build_watchlist_note(markets, earnings),
        "fallback": False,
    }


if __name__ == "__main__":
    import json
    from pathlib import Path

    logging.basicConfig(level=logging.INFO)
    fixture_path = Path(__file__).resolve().parent.parent / "tests" / "fixture_data.json"
    sample = json.loads(fixture_path.read_text())
    print(json.dumps(build_digest(sample), indent=2))
