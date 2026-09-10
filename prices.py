"""
Daily price history for every fund in the registry.

WHY THIS CACHES
---------------
Yahoo's chart endpoint is the only free source that covers TSX *and* Cboe Canada
(NEO), which is 106 of our 120 funds. It is also unofficial: Yahoo retired the
documented API in 2017 and this endpoint can change without notice. So we treat
it as a one-way tap — every bar it gives us is written to data/prices/<TICKER>.csv
and never re-fetched. After the first backfill we ask for a few days at a time,
and if the endpoint disappears tomorrow we still own the history.

We store adjusted close alongside close. For covered-call ETFs the distinction
matters more than usual: distributions are most of the total return, so a
backtest on unadjusted price would understate performance badly.
"""
import csv
import json
from urllib.request import Request, urlopen
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FUNDS = Path("data/funds.json")
# The fund data itself now lives in Supabase behind a token check, so
# data/funds.json is no longer in the repo. All this job needs is the list of
# tickers and which market each trades in — neither is worth gating — so the
# scraper leaves that behind in data/tickers.json.
TICKERS = Path("data/tickers.json")
PRICE_DIR = Path("data/prices")
SYMBOL_MAP = PRICE_DIR / "_symbols.json"
CHART = ("https://licentia-prices.megallyc.workers.dev/"
         "?symbol={sym}&range={rng}")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
}
TIME_BUDGET = 45 * 60  # leave room to commit inside the hour
BACKOFF = 3   # seconds, doubled on each retry: our own worker is not throttled
PAUSE = 1.5          # be a good citizen; this is someone else's endpoint
FULL_RANGE = "10y"   # first fetch for a fund
TOP_UP_RANGE = "1mo" # subsequent runs

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("prices")


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def candidates(ticker: str, region: str) -> list:
    """Yahoo suffixes to try. Canadian funds split across TSX (.TO) and Cboe
    Canada (.NE) with no flag in our data saying which, so try both and
    remember the answer rather than maintaining a hand-kept list."""
    t = ticker.replace(".", "-")
    if region == "CAD":
        return [f"{t}.TO", f"{t}.NE"]
    return [t, f"{t}.TO", f"{t}.NE"]


class RateLimited(RuntimeError):
    """Yahoo refused us, which is not the same as a ticker not existing.

    This distinction cost weeks. A 429 was being swallowed and returned as an
    empty list, identical to an unknown symbol, so the job wrote nothing,
    committed nothing and reported success while the price files quietly went
    stale.
    """


def fetch_bars(symbol: str, rng: str) -> list:
    """[(date, close, adjclose, volume)] oldest first, or [] if unknown."""
    try:
        data = get_json(CHART.format(sym=symbol, rng=rng))
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 401):
            return []
        if exc.code == 429:
            raise RateLimited(f"{symbol}: rate limited") from exc
        raise
    result = (data.get("chart") or {}).get("result")
    if not result:
        return []
    r = result[0]
    stamps = r.get("timestamp") or []
    quote = (r.get("indicators") or {}).get("quote") or [{}]
    closes = quote[0].get("close") or []
    volumes = quote[0].get("volume") or []
    adj = (((r.get("indicators") or {}).get("adjclose") or [{}])[0]).get("adjclose") or []
    out = []
    for i, ts in enumerate(stamps):
        close = closes[i] if i < len(closes) else None
        if close is None:
            continue          # market holiday / missing print
        a = adj[i] if i < len(adj) and adj[i] is not None else close
        v = volumes[i] if i < len(volumes) and volumes[i] is not None else ""
        day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        out.append((day, round(close, 6), round(a, 6), v))
    return out


def read_existing(path: Path) -> dict:
    if not path.exists():
        return {}
    rows = {}
    with path.open() as fh:
        for row in csv.DictReader(fh):
            rows[row["date"]] = row
    return rows


def write_csv(path: Path, rows: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "close", "adj_close", "volume"])
        for day in sorted(rows):
            r = rows[day]
            w.writerow([day, r.get("close", ""), r.get("adj_close", ""),
                        r.get("volume", "")])


def load_registry() -> dict:
    """Which funds exist, and which market each trades in.

    The fund data itself now lives in Supabase behind a token check, so
    data/funds.json is no longer in the repo. The funds endpoint returns every
    ticker to any caller — the ones a visitor cannot open come back as name and
    market only — and that is exactly what this job needs. No key required, and
    nothing worth gating is published to make it work.
    """
    url = "https://sopzbiuwakowbuqgwpmg.supabase.co/functions/v1/funds"
    try:
        req = Request(url, method="POST",
                      data=json.dumps({"seed": "price-job"}).encode(),
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=60) as r:
            payload = json.loads(r.read().decode())
        out = {}
        for f in payload.get("funds", []) + payload.get("locked", []):
            out[f["ticker"]] = {"region": f.get("region", "CAD"), "name": f.get("name")}
        if out:
            log.info("Registry: %d tickers from the funds endpoint", len(out))
            return out
        log.warning("Funds endpoint returned no tickers")
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not reach the funds endpoint (%s)", exc)

    # Falling back keeps a scheduled run alive if the endpoint is briefly down.
    for path in (TICKERS, FUNDS):
        if path.exists():
            log.info("Registry: falling back to %s", path)
            return json.loads(path.read_text())

    log.error("No ticker list available from the endpoint or on disk")
    raise SystemExit(1)


def main() -> None:
    funds = load_registry()
    PRICE_DIR.mkdir(parents=True, exist_ok=True)
    symbols = json.loads(SYMBOL_MAP.read_text()) if SYMBOL_MAP.exists() else {}

    resolved = added = unchanged = 0
    throttled = [0]
    started = time.time()
    ran_out = False
    unresolved = []

    for ticker, meta in sorted(funds.items()):
        if time.time() - started > TIME_BUDGET:
            ran_out = True
            log.warning("Time budget spent; stopping so this run can commit")
            break
        if ticker.startswith("_"):
            continue
        path = PRICE_DIR / f"{ticker}.csv"
        existing = read_existing(path)
        rng = TOP_UP_RANGE if existing else FULL_RANGE

        known = symbols.get(ticker)
        tries = [known] if known else candidates(ticker, meta.get("region", "CAD"))

        bars, used = [], None
        for sym in tries:
            for attempt in range(3):
                try:
                    bars = fetch_bars(sym, rng)
                    break
                except RateLimited:
                    throttled[0] += 1
                    wait = BACKOFF * (2 ** attempt)
                    log.warning("  %s: rate limited, waiting %ds", sym, wait)
                    time.sleep(wait)
                    bars = []
                except Exception as exc:  # noqa: BLE001
                    log.warning("  %s via %s failed: %s", ticker, sym, exc)
                    bars = []
                    break
            time.sleep(PAUSE)
            if bars:
                used = sym
                break

        if not bars:
            unresolved.append(ticker)
            log.warning("%s: no price data (tried %s)", ticker, ", ".join(str(t) for t in tries))
            continue

        if used != known:
            symbols[ticker] = used
            resolved += 1

        before = len(existing)
        for day, close, adj, vol in bars:
            existing[day] = {"close": close, "adj_close": adj, "volume": vol}
        new = len(existing) - before
        if new:
            added += new
            log.info("%s (%s): +%d bars, %d total, %s..%s",
                     ticker, used, new, len(existing), min(existing), max(existing))
        else:
            unchanged += 1
        write_csv(path, existing)

    SYMBOL_MAP.write_text(json.dumps(symbols, indent=2, sort_keys=True))

    total_files = len(list(PRICE_DIR.glob("*.csv")))
    log.info("Done — %d funds with price files, %d new bars, %d symbols resolved, "
             "%d already current, %d unresolved",
             total_files, added, resolved, unchanged, len(unresolved))
    if unresolved:
        log.warning("No price data for: %s", ", ".join(unresolved))

    # A job that fetched nothing should not report success. Silence here is
    # what let the price files sit weeks out of date.
    if ran_out:
        log.warning("Stopped early: %d of %d funds done", resolved, len(funds))

    if throttled[0] and not added:
        raise SystemExit(
            f"Yahoo rate limited every request ({throttled[0]} refusals) "
            f"and no new bars were written")


if __name__ == "__main__":
    main()
