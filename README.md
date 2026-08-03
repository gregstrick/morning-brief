# Morning Brief

A static, installable web app (PWA) that publishes a pre-market briefing every trading day at ~7:40 AM
Central — futures, overnight action, rates, today's economic calendar and Fed speakers, earnings,
pre-market movers, a personal watchlist, headlines, and a computed morning digest up top. Built by a Python
pipeline on a GitHub Actions schedule, hosted free on GitHub Pages. No paid services, no API keys required.

The page is organized into four tabs (the masthead/countdown and footer are always visible above/below
them):

1. **Summary** — the morning digest, futures & overnight, rates & money, yesterday's recap. Everything you
   need in 90 seconds. The digest (headline + four short blocks) isn't AI-written — it's computed straight
   from the same market/calendar/earnings data below it by [`src/digest.py`](src/digest.py): plain Python
   rules (biggest overnight mover, today's highest-impact release, any watchlist name reporting earnings,
   etc.), so there's no API key, no cost, and no third-party ToS to worry about.
2. **News & Calendar** — today's economic releases and Fed speakers, today's earnings reporters, headlines
   from multiple reputable sources (CNBC, MarketWatch, Yahoo Finance).
3. **Movers** — today's biggest pre-market gainers/losers (outliers) across the scan universe.
4. **Watchlist** — your configured tickers, with a **Customize** toggle to show/hide and reorder them
   (saved in your browser), plus an optional **Quick Lookup** box for live quotes on any ticker — see
   [Live ticker lookup](#live-ticker-lookup-optional) below.

Full product spec: [`MorningBrief_Build_Spec.md`](MorningBrief_Build_Spec.md) (note: the spec's original
design used an AI-written synthesis; that was swapped for the free deterministic digest above, everything
else matches).

## One-time setup

1. **Enable Pages.** Repo → Settings → Pages → Source: **GitHub Actions**.
2. **(Optional) Add a Finnhub key.** Register a free key at [finnhub.io](https://finnhub.io) and add it as
   repo secret `FINNHUB_API_KEY` — only used as a fallback if Nasdaq's earnings API blocks the runner. Not
   required; the earnings card just says "unavailable" without it.
3. **First run.** Actions tab → *Build Morning Brief* → **Run workflow**. Check **force** if you want a
   live page right now regardless of what day it is (the scheduled run only publishes on trading days —
   `force` bypasses that guard for on-demand testing). Green check → the brief is live at
   `https://<username>.github.io/morning-brief/`.
4. **Install it as an app.** It's a PWA, so any Chromium or Safari browser can install it as a standalone
   window with its own icon — same brief, same URL, on every device:
   - **iPhone:** open the URL in Safari → Share → **Add to Home Screen**.
   - **Mac:** Chrome/Edge's install icon (a monitor-with-arrow) in the address bar, or Safari → File →
     **Add to Dock**.
   - **Windows PC:** open the URL in Chrome or Edge → the install icon in the address bar (or menu → **Apps
     → Install this site as an app**) → it lands in the Start Menu and taskbar like any other app.
5. Edit `config/config.yml` any time to change the watchlist, universe, or feeds — commit and it takes
   effect on the next scheduled run (or trigger the workflow manually to see it now).

## Local development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python -m src.build --force             # build right now with live data
.venv/bin/python -m src.build --fixture           # build from tests/fixture_data.json, no network

.venv/bin/python -m http.server 8000 -d site/dist # preview at http://localhost:8000
```

Each fetcher is independently runnable, e.g. `python -m src.fetch_markets`.

Note: the service worker is network-first for navigations but can still serve a cached page during local
iteration — hard-reload or bump the `CACHE` constant in `site/sw.js` if a stale page is confusing you.

## Feed sources (where each card's data comes from)

| Card | Source | Notes |
|---|---|---|
| This Morning digest | Computed from the rows below by `src/digest.py` | No API, no cost, never blocks the build |
| Futures, rates, FX, commodities, crypto, watchlist, movers, sectors | Yahoo Finance via `yfinance` | Unofficial/scraped; pin the version in `requirements.txt` |
| Economic calendar | ForexFactory weekly feed, URL in `config.yml` (`economic_calendar_url`) | If it ever 404s, check the ForexFactory calendar-widget docs for the current feed URL |
| Earnings | Nasdaq calendar API, Finnhub fallback | Nasdaq occasionally blocks datacenter IPs (GitHub runners); Finnhub needs `FINNHUB_API_KEY` |
| Headlines | RSS feeds listed in `config.yml` (`rss_feeds`) | CNBC, MarketWatch, Yahoo Finance |
| Watchlist tab's Quick Lookup | Your own Cloudflare Worker (optional) → Yahoo Finance | See below; blank `quote_proxy_url` just hides the box |

A card showing "Data unavailable this morning" for more than a few days in a row usually means a feed URL
moved — check the corresponding row above first.

## Live ticker lookup (optional)

The Watchlist tab's **Quick Lookup** box fetches a live quote for any ticker you type, straight from your
browser. Yahoo Finance doesn't allow direct cross-origin requests from a browser (no CORS header — verified,
not assumed), so this needs one small piece of infrastructure between your phone/browser and Yahoo: a free
[Cloudflare Worker](https://workers.cloudflare.com/) that forwards the request and adds the header back.
This is the only non-static piece of the whole project; skip this section entirely and the rest of the app
works exactly the same, just without the Quick Lookup box.

1. Sign up for a free Cloudflare account (no credit card required for the Workers free tier) and go to
   **Workers & Pages → Create → Create Worker**.
2. Replace the default script with the contents of [`cloudflare-worker/quote-proxy.js`](cloudflare-worker/quote-proxy.js)
   and click **Deploy**.
3. In that file, set `ALLOWED_ORIGIN` to your Pages URL (`https://<username>.github.io`) — this is what
   restricts who can use your Worker — then redeploy.
4. Copy the Worker's URL (looks like `https://quote-proxy.<your-subdomain>.workers.dev`) into
   `config/config.yml`'s `quote_proxy_url`, commit, and the Quick Lookup box appears on the next build.

The Worker only proxies `v8/finance/chart` (plain price + previous close, no crumb/cookie auth needed —
it's the same endpoint the daily pipeline already uses successfully), caps each request at 5 symbols, and
sets `Cache-Control: no-store`. It costs nothing on Cloudflare's free tier (100,000 requests/day) for
single-user use.

## Ops notes

- **Cron drift:** GitHub scheduled workflows can start several minutes late; the 7:40 AM CT schedule leaves
  buffer before the 8:30 AM bell.
- **DST:** two crons (CDT/CST) plus an hour guard in `src/build.py` keep exactly one real run per day at
  7 AM CT year-round.
- **60-day pause:** GitHub disables scheduled workflows after 60 days with no repo activity. Any commit
  (even a watchlist tweak) resets the clock.
- **Guard exits never wipe the live page:** the workflow only uploads/deploys when `src/build.py` reports
  `built=true`; a guard exit (holiday, wrong hour) leaves the previous Pages deployment untouched.

---

Informational only — not investment advice.
