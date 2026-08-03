/**
 * Morning Brief — live quote proxy.
 *
 * The watchlist tab's "add a ticker" box needs a live price for symbols that
 * aren't in config.yml, fetched straight from the reader's browser. Yahoo
 * Finance doesn't send CORS headers, so a browser `fetch()` against it fails
 * outright (confirmed live: the request succeeds in no-cors mode but the
 * response can't be read). This Worker does the one thing a static GitHub
 * Pages site can't: sit between the browser and Yahoo, forward the request
 * server-to-server (no CORS restriction there), and add the header back in.
 *
 * Deliberately hits the same Yahoo endpoint (v8/finance/chart) that
 * yfinance's fast_info/history calls use server-side in the daily pipeline —
 * that endpoint doesn't need the cookie+crumb dance Yahoo requires for its
 * richer endpoints (quoteSummary, options, etc.), so this stays a plain
 * fetch-and-forward with no session state to manage.
 *
 * Deploy: Cloudflare dashboard -> Workers & Pages -> Create Worker -> paste
 * this file's contents -> Deploy. Then set ALLOWED_ORIGIN below (or as a
 * Worker environment variable) to your Pages URL, and put the Worker's URL
 * into config.yml's quote_proxy_url.
 */

const ALLOWED_ORIGIN = "https://gregstrick.github.io";
const SYMBOL_RE = /^[A-Za-z0-9.\-=^]{1,12}$/;

function corsHeaders(origin) {
  return {
    "Access-Control-Allow-Origin": origin === ALLOWED_ORIGIN ? origin : ALLOWED_ORIGIN,
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Cache-Control": "no-store",
  };
}

async function fetchQuote(symbol) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}`;
  const res = await fetch(url, {
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      Accept: "application/json",
    },
  });

  if (!res.ok) {
    return { symbol, error: `upstream ${res.status}` };
  }

  const data = await res.json();
  const result = data?.chart?.result?.[0];
  if (!result || data?.chart?.error) {
    return { symbol, error: "not found" };
  }

  const meta = result.meta || {};
  const price = meta.regularMarketPrice ?? null;
  const prevClose = meta.previousClose ?? meta.chartPreviousClose ?? null;
  const changePct = price != null && prevClose ? ((price - prevClose) / prevClose) * 100 : null;

  return {
    symbol: meta.symbol || symbol,
    name: meta.shortName || meta.longName || null,
    price,
    prevClose,
    changePct: changePct != null ? Math.round(changePct * 100) / 100 : null,
    currency: meta.currency || null,
    marketState: meta.marketState || null,
    asOf: meta.regularMarketTime ? meta.regularMarketTime * 1000 : null,
  };
}

export default {
  async fetch(request) {
    const origin = request.headers.get("Origin") || "";
    const headers = corsHeaders(origin);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers });
    }

    const url = new URL(request.url);
    const raw = url.searchParams.get("symbols") || url.searchParams.get("symbol") || "";
    const symbols = raw
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter((s) => s && SYMBOL_RE.test(s))
      .slice(0, 5); // small, deliberate cap -- this is a one-off lookup box, not a bulk quote API

    if (symbols.length === 0) {
      return new Response(JSON.stringify({ error: "no valid symbols" }), {
        status: 400,
        headers: { ...headers, "Content-Type": "application/json" },
      });
    }

    const quotes = await Promise.all(symbols.map(fetchQuote));

    return new Response(JSON.stringify({ quotes }), {
      status: 200,
      headers: { ...headers, "Content-Type": "application/json" },
    });
  },
};
