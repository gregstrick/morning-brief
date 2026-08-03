"""AI synthesis (Claude API): turns the assembled data dict into the voice of the brief.

Independently runnable against a fixture: `python -m src.synthesize` (uses tests/fixture_data.json
if present, else a tiny built-in sample) and prints the resulting JSON.
"""
import json
import logging
import re

from src.util import load_config, now_ct

logger = logging.getLogger("morning_brief")

SYSTEM_PROMPT = """You are the pre-market analyst writing a private daily brief for one reader:
a retail investor and small-business owner who wants situational awareness
before the 8:30 AM Central open. He runs an electronics resale business, so
memory/storage pricing (Micron, SanDisk, WDC), PC OEMs (Dell, HP), Apple
hardware, and eBay are of particular interest when relevant.

Rules:
- Use ONLY the data provided in the message. Never invent numbers, events,
  or news. If a section's data is missing, say so in one clause and move on.
- Plain English, concise, zero hype. Numbers over adjectives.
- No investment advice. Never suggest buying, selling, or positioning.
  Describe what is happening and what is scheduled, not what to do.
- All times are already in Central Time; refer to them as given.
- Output ONLY a JSON object, no markdown fences, no preamble, matching:
  {
    "headline":       string,  // <= 18 words, the morning in one line
    "overnight":      string,  // ~80 words: futures, Asia/Europe, rates/dollar/oil, anything that moved and the apparent driver from the headlines
    "today_setup":    string,  // ~90 words: today's data releases, Fed speakers, notable earnings, and what each could plausibly swing
    "risk_watch":     string,  // ~60 words: the one or two things most likely to change the tape today
    "watchlist_note": string   // ~50 words: only if the data actually touches the reader's tickers or the memory/PC/eBay complex; otherwise "Nothing notable for the watchlist this morning."
  }"""

FALLBACK = {
    "headline": "Synthesis unavailable this morning — data below is live.",
    "overnight": "",
    "today_setup": "",
    "risk_watch": "",
    "watchlist_note": "",
    "fallback": True,
}

RETRY_NOTICE = "\n\nYour last reply was not valid JSON. Reply with only the JSON object."

REQUIRED_KEYS = {"headline", "overnight", "today_setup", "risk_watch", "watchlist_note"}

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_nulls(obj):
    """Recursively drop None values from dicts/lists to keep the prompt compact."""
    if isinstance(obj, dict):
        return {k: _strip_nulls(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_strip_nulls(v) for v in obj if v is not None]
    return obj


def build_user_prompt(data: dict, early_close: bool = False) -> str:
    now = now_ct()
    header = f"Date: {now.strftime('%A')}, {now.strftime('%B %-d, %Y')}. Market opens 8:30 AM CT."
    if early_close:
        header += " Early close 12:00 PM CT."

    sections = {
        "FUTURES/OVERNIGHT": {
            "futures": data.get("markets", {}).get("futures"),
            "volatility": data.get("markets", {}).get("volatility"),
            "international": data.get("markets", {}).get("international"),
        },
        "RATES": data.get("markets", {}).get("rates"),
        "DOLLAR-COMMODITIES-CRYPTO": data.get("markets", {}).get("dollar_commodities_crypto"),
        "ECONOMIC CALENDAR TODAY": (data.get("calendar") or {}).get("events"),
        "EARNINGS TODAY": data.get("earnings"),
        "PREMARKET MOVERS": data.get("markets", {}).get("movers"),
        "WATCHLIST": data.get("markets", {}).get("watchlist"),
        "YESTERDAY RECAP": data.get("markets", {}).get("recap"),
        "HEADLINES": [
            {"title": h["title"], "source": h["source"]}
            for h in (data.get("news") or {}).get("headlines", [])
        ],
    }
    sections = _strip_nulls(sections)

    body = "\n\n".join(f"{label}:\n{json.dumps(payload, separators=(',', ':'))}" for label, payload in sections.items())
    return f"{header}\n\n{body}"


def _extract_json(text: str) -> dict:
    cleaned = _CODE_FENCE_RE.sub("", text.strip()).strip()
    parsed = json.loads(cleaned)
    if not REQUIRED_KEYS.issubset(parsed.keys()):
        raise ValueError(f"Missing required keys: {REQUIRED_KEYS - parsed.keys()}")
    return parsed


def synthesize(data: dict, cfg: dict = None, no_synth: bool = False, early_close: bool = False) -> dict:
    if no_synth:
        return {**FALLBACK, "headline": "Synthesis skipped (--no-synth) — data below is live."}

    cfg = cfg or load_config()
    user_prompt = build_user_prompt(data, early_close=early_close)

    try:
        from anthropic import Anthropic

        client = Anthropic()
        messages = [{"role": "user", "content": user_prompt}]

        for attempt in range(2):
            msg = client.messages.create(
                model=cfg["model"],
                max_tokens=1200,
                system=SYSTEM_PROMPT,
                messages=messages,
            )
            logger.info("synthesize: usage=%s attempt=%d", msg.usage, attempt + 1)
            text = "".join(block.text for block in msg.content if block.type == "text")
            try:
                result = _extract_json(text)
                result["fallback"] = False
                return result
            except (json.JSONDecodeError, ValueError):
                logger.warning("synthesize: malformed JSON on attempt %d", attempt + 1)
                messages = [
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": RETRY_NOTICE},
                ]
        logger.error("synthesize: giving up after retry, using fallback")
    except Exception:
        logger.exception("synthesize: API call failed, using fallback")

    return dict(FALLBACK)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    logging.basicConfig(level=logging.INFO)
    fixture_path = Path(__file__).resolve().parent.parent / "tests" / "fixture_data.json"
    if fixture_path.exists():
        sample = json.loads(fixture_path.read_text())
    else:
        sample = {
            "markets": {"futures": {"symbol": "ES=F", "last": 5000, "prev_close": 4990, "change_pct": 0.2}},
            "calendar": {"events": []},
            "earnings": {},
            "news": {"headlines": []},
        }
    no_synth = "--no-synth" in sys.argv
    print(json.dumps(synthesize(sample, no_synth=no_synth), indent=2, default=str))
