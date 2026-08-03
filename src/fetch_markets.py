"""Markets fetcher (yfinance): futures, indices, rates, FX, commodities, crypto, watchlist, sectors, movers.

Independently runnable: `python -m src.fetch_markets` prints its JSON.
"""
import json
import logging

import yfinance as yf

from src.util import load_config, now_ct, retry, safe

logger = logging.getLogger("morning_brief")


def _pct(last, prev):
    if last is None or prev in (None, 0):
        return None
    return round((last - prev) / prev * 100, 4)


@retry(times=2, backoff=1.5)
def _batch_fast_info(symbols: list) -> dict:
    """Batch-fetch fast_info for a list of symbols. Returns {symbol: {last, prev_close} | None}."""
    if not symbols:
        return {}
    tk = yf.Tickers(" ".join(symbols))
    out = {}
    for sym in symbols:
        try:
            fi = tk.tickers[sym].fast_info
            out[sym] = {"last": fi.get("lastPrice"), "prev_close": fi.get("previousClose")}
        except Exception:
            out[sym] = None
    return out


@retry(times=2, backoff=1.5)
def _history_last_two_closes(symbol: str):
    h = yf.Ticker(symbol).history(period="5d")
    if h is None or len(h) < 2:
        return None
    closes = h["Close"].dropna()
    if len(closes) < 2:
        return None
    return float(closes.iloc[-1]), float(closes.iloc[-2])


def _snapshot_block(symbol_map: dict) -> list:
    """symbol_map: {symbol: label}. Returns [{symbol, name, last, prev_close, change_pct}]."""
    symbols = list(symbol_map.keys())
    batch = safe(_batch_fast_info, symbols) or {}
    rows = []
    for sym, label in symbol_map.items():
        info = batch.get(sym)
        last = info.get("last") if info else None
        prev = info.get("prev_close") if info else None
        if last is None or prev is None:
            fallback = safe(_history_last_two_closes, sym)
            if fallback:
                last, prev = fallback
        rows.append(
            {
                "symbol": sym,
                "name": label,
                "last": last,
                "prev_close": prev,
                "change_pct": _pct(last, prev),
            }
        )
    return rows


def fetch_rates(cfg: dict) -> list:
    """CBOE yield indexes (^IRX/^FVX/^TNX/^TYX). Current yfinance/Yahoo data already reports the
    level as a plain percentage (e.g. ^TNX lastPrice=4.745 means 4.745%) rather than the historical
    yield-x10 convention -- verified live rather than assumed, since this exact field has drifted
    before and the spec flags yfinance breakage as a known risk (see README's feed-sources table).
    Reports level in % and change in bp (1 percentage point = 100 bp).
    """
    raw = _snapshot_block(cfg["rates"])
    rows = []
    for r in raw:
        last_pct = round(r["last"], 3) if r["last"] is not None else None
        prev_pct = round(r["prev_close"], 3) if r["prev_close"] is not None else None
        bp_change = round((r["last"] - r["prev_close"]) * 100, 1) if (r["last"] is not None and r["prev_close"] is not None) else None
        rows.append(
            {
                "symbol": r["symbol"],
                "name": r["name"],
                "yield_pct": last_pct,
                "prev_yield_pct": prev_pct,
                "change_bp": bp_change,
            }
        )
    return rows


def fetch_recap(cfg: dict) -> dict:
    """Yesterday's closes for indices_recap; sector leaders/laggards ranked by % change."""
    symbol_map = {**cfg["indices_recap"], **cfg["sectors"]}
    symbols = list(symbol_map.keys())
    df = yf.download(symbols, period="5d", interval="1d", progress=False, auto_adjust=True)
    close = df["Close"]

    def last_two(sym):
        col = close[sym].dropna()
        if len(col) < 2:
            return None, None
        return float(col.iloc[-1]), float(col.iloc[-2])

    indices = []
    for sym, label in cfg["indices_recap"].items():
        last, prev = last_two(sym)
        indices.append({"symbol": sym, "name": label, "last": last, "prev_close": prev, "change_pct": _pct(last, prev)})

    sector_rows = []
    for sym, label in cfg["sectors"].items():
        last, prev = last_two(sym)
        sector_rows.append({"symbol": sym, "name": label, "last": last, "prev_close": prev, "change_pct": _pct(last, prev)})

    ranked = sorted([s for s in sector_rows if s["change_pct"] is not None], key=lambda s: s["change_pct"], reverse=True)
    return {
        "indices": indices,
        "sector_leaders": ranked[:3],
        "sector_laggards": list(reversed(ranked[-3:])) if len(ranked) >= 3 else list(reversed(ranked)),
    }


@retry(times=2, backoff=1.5)
def _premarket_quote(symbol: str) -> dict:
    """Fallback chain: 1) get_info() preMarket* fields, 2) 1m prepost history, 3) fast_info regular session."""
    ticker = yf.Ticker(symbol)

    try:
        info = ticker.get_info()
    except Exception:
        info = {}
    prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
    pre_price = info.get("preMarketPrice")
    pre_pct = info.get("preMarketChangePercent")
    if pre_price is not None and prev_close is not None:
        return {
            "prev_close": prev_close,
            "premarket_price": pre_price,
            "premarket_pct": round(pre_pct, 4) if pre_pct is not None else _pct(pre_price, prev_close),
            "session": "pre",
        }

    try:
        h = ticker.history(period="1d", interval="1m", prepost=True)
    except Exception:
        h = None
    if h is not None and len(h) > 0 and prev_close is not None:
        last_row_price = float(h["Close"].dropna().iloc[-1])
        return {
            "prev_close": prev_close,
            "premarket_price": last_row_price,
            "premarket_pct": _pct(last_row_price, prev_close),
            "session": "pre",
        }

    fi = ticker.fast_info
    last = fi.get("lastPrice")
    prev = fi.get("previousClose") or prev_close
    return {
        "prev_close": prev,
        "premarket_price": last,
        "premarket_pct": _pct(last, prev),
        "session": "prev",
    }


def fetch_watchlist(cfg: dict) -> dict:
    """Grouped watchlist pre-market quotes: {group: [{symbol, name, prev_close, premarket_price, premarket_pct, session}]}."""
    groups = {}
    for group, symbols in cfg["watchlist"].items():
        rows = []
        for sym, name in symbols.items():
            q = safe(_premarket_quote, sym)
            row = {"symbol": sym, "name": name}
            if q:
                row.update(q)
            else:
                row.update({"prev_close": None, "premarket_price": None, "premarket_pct": None, "session": None})
            rows.append(row)
        groups[group] = rows
    return groups


def fetch_universe_quotes(cfg: dict, extra_symbols=None) -> list:
    """Flat pre-market quotes for the movers universe, merged with watchlist symbols and any extra (earnings) symbols."""
    symbols = set(cfg["universe"])
    for group_syms in cfg["watchlist"].values():
        symbols.update(group_syms.keys())
    if extra_symbols:
        symbols.update(extra_symbols)

    rows = []
    for sym in sorted(symbols):
        q = safe(_premarket_quote, sym)
        if not q:
            continue
        rows.append({"symbol": sym, **q})
    return rows


MOVERS_SHOWN = 8


def fetch_movers(cfg: dict, extra_symbols=None) -> dict:
    """Top gainers / losers among the universe (drops symbols with no genuine pre-market print)."""
    quotes = fetch_universe_quotes(cfg, extra_symbols=extra_symbols)
    genuine = [q for q in quotes if q.get("session") == "pre" and q.get("premarket_pct") is not None]
    ranked = sorted(genuine, key=lambda q: q["premarket_pct"], reverse=True)
    n = MOVERS_SHOWN
    return {
        "gainers": ranked[:n],
        "losers": list(reversed(ranked[-n:])) if len(ranked) >= n else list(reversed(ranked)),
    }


def fetch_markets(cfg: dict = None, extra_mover_symbols=None) -> dict:
    cfg = cfg or load_config()
    return {
        "fetched_at": now_ct().isoformat(),
        "futures": safe(_snapshot_block, cfg["futures"]),
        "volatility": safe(_snapshot_block, cfg["volatility"]),
        "international": safe(_snapshot_block, cfg["international"]),
        "rates": safe(fetch_rates, cfg),
        "dollar_commodities_crypto": safe(_snapshot_block, cfg["dollar_commodities_crypto"]),
        "recap": safe(fetch_recap, cfg),
        "watchlist": safe(fetch_watchlist, cfg),
        "movers": safe(fetch_movers, cfg, extra_mover_symbols),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(fetch_markets(), indent=2, default=str))
