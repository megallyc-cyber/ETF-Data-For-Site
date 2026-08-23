"""
Turn the delta-encoded price batches into one CSV per fund.

WHY BATCHES EXIST AT ALL
------------------------
Yahoo answers a browser but returns 429 to GitHub Actions, so the history was
fetched client-side and shipped here as compressed batches. This script is the
other half: pure local computation, no network, so it runs anywhere and can
never be rate limited.

WIRE FORMAT
-----------
{"TICKER": {"s": "HMAX.TO",
            "d": "19391,1,1,3,..."   day numbers since epoch, first absolute then gaps
            "p": "173400,-50,25,..." adjusted close x10000, first absolute then deltas
           }}
Both series are the same length; a fund's CSV is written newest-last so it can
be appended to later.
"""
import csv
import json
import logging
from datetime import date, timedelta
from pathlib import Path

RAW = Path("data/prices_raw")
OUT = Path("data/prices")
EPOCH = date(1970, 1, 1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("expand")


def decode(entry: dict) -> list:
    """[(iso_date, adj_close)] oldest first."""
    days = [int(x) for x in entry["d"].split(",") if x != ""]
    cents = [int(x) for x in entry["p"].split(",") if x != ""]
    if len(days) != len(cents):
        raise ValueError(f"length mismatch: {len(days)} dates vs {len(cents)} prices")
    rows, day, price = [], 0, 0
    for i, (dd, dp) in enumerate(zip(days, cents)):
        day = dd if i == 0 else day + dd
        price = dp if i == 0 else price + dp
        rows.append(((EPOCH + timedelta(days=day)).isoformat(), round(price / 10000, 4)))
    return rows


def main() -> None:
    batches = sorted(RAW.glob("batch*.json"))
    if not batches:
        raise SystemExit("no batches in data/prices_raw — nothing to expand")

    OUT.mkdir(parents=True, exist_ok=True)
    symbols = {}
    written = total_rows = 0
    problems = []

    for path in batches:
        data = json.loads(path.read_text())
        for ticker, entry in sorted(data.items()):
            try:
                rows = decode(entry)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{ticker}: {exc}")
                continue
            if not rows:
                problems.append(f"{ticker}: no rows")
                continue

            # sanity: a fund whose adjusted close goes to zero or negative means
            # the delta chain drifted, and a silently wrong price series is worse
            # than a missing one.
            lo = min(p for _, p in rows)
            if lo <= 0:
                problems.append(f"{ticker}: non-positive price {lo}")
                continue

            with (OUT / f"{ticker}.csv").open("w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["date", "adj_close"])
                w.writerows(rows)
            symbols[ticker] = {"symbol": entry.get("s", ""), "bars": len(rows),
                               "first": rows[0][0], "last": rows[-1][0]}
            written += 1
            total_rows += len(rows)

    (OUT / "_index.json").write_text(json.dumps(symbols, indent=2, sort_keys=True))

    log.info("Expanded %d funds, %d rows total from %d batches",
             written, total_rows, len(batches))
    if problems:
        log.warning("Skipped %d: %s", len(problems), "; ".join(problems[:10]))
    if not written:
        raise SystemExit("expanded zero funds — refusing to report success")


if __name__ == "__main__":
    main()
