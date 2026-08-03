# Morning Brief

A static, installable web app (PWA) that publishes a pre-market briefing every trading day at ~7:40 AM
Central — futures, overnight action, rates, today's economic calendar and Fed speakers, earnings,
pre-market movers, a personal watchlist, headlines, and an AI-written synthesis up top. Built by a Python
pipeline on a GitHub Actions schedule, hosted free on GitHub Pages.

The page is organized into four tabs (the masthead/countdown and footer are always visible above/below
them):

1. **Summary** — the AI synthesis, futures & overnight, rates & money, yesterday's recap. Everything you
   need in 90 seconds.
2. **News & Calendar** — today's economic releases and Fed speakers, today's earnings reporters, headlines.
3. **Movers** — today's biggest pre-market gainers/losers (outliers) across the scan universe.
4. **Watchlist** — your configured tickers, with a **Customize** toggle to show/hide and reorder them
   (saved in your browser), plus an optional **Quick Lookup** box for live quotes on any ticker — see
   [Live ticker lookup](#live-ticker-lookup-optional) below.

Full product spec: [`MorningBrief_Build_Spec.md`](MorningBrief_Build_Spec.md).

## One-time setup

1. **Enable Pages.** Repo → Settings → Pages → Source: **GitHub Actions**.
2. **Get an API key.** [console.anthropic.com](https://console.anthropic.com) → API Keys → create key.
   This is the Claude **API** (usage-billed, separate from a Claude Pro subscription) — add a few dollars
   of credit; at roughly 3¢/day of usage that's several months of briefs.
3. **Add secrets.** Repo → Settings → Secrets and variables → Actions → new secret `ANTHROPIC_API_KEY`.
   Optionally register a free key at [finnhub.io](https://finnhub.io) and add `FINNHUB_API_KEY` as a
   fallback for the earnings calendar.
4. **First run.** Actions tab → *Build Morning Brief* → **Run workflow**. Green check → the brief is live
   at `https://<username>.github.io/morning-brief/`.
5. **Install it.**
   - **iPhone:** open the URL in Safari → Share → **Add to Home Screen**.
   - **Mac:** Chrome's install icon in the address bar, or Safari → File → **Add to Dock**.
6. Edit `config/config.yml` any time to change the watchlist, universe, or feeds — commit and it takes
   effect on the next scheduled run (or trigger the workflow manually to see it now).

## Local development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python -m src.build --force            # build right now with live data
.venv/bin/python -m src.build --force --no-synth  # same, but skip the Claude call (no token spend)
.venv/bin/python -m src.build --fixture           # build from tests/fixture_data.json, no network

.venv/bin/python -m http.server 8000 -d site/dist # preview at http://localhost:8000
```

Each fetcher is independently runnable, e.g. `python -m src.fetch_markets`.

Note: the service worker is network-first for navigations but can still serve a cached page during local
iteration — hard-reload or bump the `CACHE` constant in `site/sw.js` if a stale page is confusing you.

## Feed sources (where each card's data comes from)

| Card | Source | Notes |
|---|---|---|
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
