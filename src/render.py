"""Renderer: Jinja2 template -> site/dist/index.html (+ data.json, PWA assets)."""
import json
import logging
import shutil
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.util import REPO_ROOT, now_ct

logger = logging.getLogger("morning_brief")

SITE_DIR = REPO_ROOT / "site"
DIST_DIR = SITE_DIR / "dist"

GITHUB_URL = "https://github.com/gregstrick/morning-brief"


def fmt_pct(value):
    if value is None:
        return "—"
    s = f"{value:+.1f}%"
    return s.replace("-", "−")


def fmt_price(value):
    if value is None:
        return "—"
    return f"{value:,.2f}"


def fmt_bp(value):
    if value is None:
        return "—"
    s = f"{value:+.1f} bp"
    return s.replace("-", "−")


def age_ago(iso_str):
    if not iso_str:
        return ""
    then = datetime.fromisoformat(iso_str)
    delta = now_ct() - then
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(SITE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["fmt_pct"] = fmt_pct
    env.filters["fmt_price"] = fmt_price
    env.filters["fmt_bp"] = fmt_bp
    env.filters["age_ago"] = age_ago
    return env


def render(data: dict, synthesis: dict, cfg: dict, ctx: dict) -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    env = _env()
    template = env.get_template("template.html")
    html = template.render(
        cfg=cfg,
        data=data,
        synthesis=synthesis,
        github_url=GITHUB_URL,
        **ctx,
    )
    (DIST_DIR / "index.html").write_text(html, encoding="utf-8")
    (DIST_DIR / "data.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    shutil.copy(SITE_DIR / "manifest.webmanifest", DIST_DIR / "manifest.webmanifest")
    shutil.copy(SITE_DIR / "sw.js", DIST_DIR / "sw.js")

    icons_src = SITE_DIR / "icons"
    icons_dst = DIST_DIR / "icons"
    if icons_src.exists():
        icons_dst.mkdir(exist_ok=True)
        for f in icons_src.iterdir():
            shutil.copy(f, icons_dst / f.name)

    size_kb = (DIST_DIR / "index.html").stat().st_size / 1024
    logger.info("render: wrote index.html (%.1f KB)", size_kb)
