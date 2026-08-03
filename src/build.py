"""Orchestrator: session/hour guards, fetch, compute the digest, render.

CLI:
    python -m src.build              # normal (guarded) run
    python -m src.build --force      # bypass hour + session guards, build now with live data
    python -m src.build --fixture    # build from tests/fixture_data.json instead of the network
"""
import argparse
import json
import logging
import os
import sys

import pandas_market_calendars as mcal

from src import digest as digest_module
from src import fetch_calendar, fetch_earnings, fetch_markets, fetch_news, render
from src.util import CT, REPO_ROOT, load_config, now_ct, safe

logger = logging.getLogger("morning_brief")

FIXTURE_PATH = REPO_ROOT / "tests" / "fixture_data.json"
NORMAL_CLOSE_HOUR_CT = 15  # 3:00 PM CT


def session_info():
    """NYSE session guard + today's open/close (CT) for the countdown, per §5.5."""
    nyse = mcal.get_calendar("NYSE")
    today = now_ct().date()
    sched = nyse.schedule(start_date=today, end_date=today)
    if sched.empty:
        return {
            "is_session": False,
            "early_close": False,
            "market_open_epoch_ms": None,
            "market_close_epoch_ms": None,
            "banner": f"Markets closed today — this is the {_last_session_label(nyse, today)} edition"
            if _has_prior_edition()
            else "Markets closed today.",
        }

    open_dt = sched.iloc[0]["market_open"].tz_convert(CT)
    close_dt = sched.iloc[0]["market_close"].tz_convert(CT)
    early_close = close_dt.hour < NORMAL_CLOSE_HOUR_CT

    return {
        "is_session": True,
        "early_close": early_close,
        "market_open_epoch_ms": int(open_dt.timestamp() * 1000),
        "market_close_epoch_ms": int(close_dt.timestamp() * 1000),
        "banner": None,
    }


def _has_prior_edition() -> bool:
    return (render.DIST_DIR / "index.html").exists()


def _last_session_label(nyse, today) -> str:
    prior = nyse.schedule(start_date=today.replace(day=1), end_date=today)
    if prior.empty:
        return "previous"
    last_session_date = prior.index[-1].date()
    return last_session_date.strftime("%A")


def assemble_data(cfg: dict) -> dict:
    earnings = safe(fetch_earnings.fetch_earnings, cfg) or {}
    notable_reporters = [e["symbol"] for e in (earnings.get("before_open", {}).get("shown", []) + earnings.get("after_close", {}).get("shown", []))]

    return {
        "fetched_at": now_ct().isoformat(),
        "markets": safe(fetch_markets.fetch_markets, cfg, notable_reporters),
        "calendar": safe(fetch_calendar.fetch_calendar, cfg),
        "earnings": earnings,
        "news": safe(fetch_news.fetch_news, cfg),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="bypass hour + session guards")
    parser.add_argument("--fixture", action="store_true", help="build from tests/fixture_data.json")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    event_name = os.environ.get("GITHUB_EVENT_NAME")
    if event_name == "schedule" and not args.force:
        if now_ct().hour != 7:
            logger.info("Guard: outside 7 AM CT hour (dual-cron DST guard). Exiting 0.")
            print("built=false")
            sys.exit(0)

    cfg = load_config()
    sess = session_info()

    if not sess["is_session"] and not args.force:
        logger.info("Guard: not an NYSE session today. Exiting 0.")
        print("built=false")
        sys.exit(0)

    if args.fixture:
        if not FIXTURE_PATH.exists():
            logger.error("--fixture requested but %s does not exist", FIXTURE_PATH)
            sys.exit(1)
        data = json.loads(FIXTURE_PATH.read_text())
        logger.info("Loaded fixture data from %s", FIXTURE_PATH)
    else:
        data = assemble_data(cfg)
        if args.force:
            FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
            FIXTURE_PATH.write_text(json.dumps(data, indent=2, default=str))
            logger.info("Saved fixture snapshot to %s", FIXTURE_PATH)

    digest = digest_module.build_digest(data, early_close=sess["early_close"])

    ctx = {
        "generated_at": now_ct(),
        "edition_date": now_ct(),
        "is_session": sess["is_session"],
        "early_close": sess["early_close"],
        "market_open_epoch_ms": sess["market_open_epoch_ms"],
        "market_close_epoch_ms": sess["market_close_epoch_ms"],
        "banner": sess["banner"],
    }
    render.render(data, digest, cfg, ctx)
    logger.info("Build complete.")
    print("built=true")


if __name__ == "__main__":
    main()
