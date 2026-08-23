"""
Which price source will actually talk to a GitHub Actions runner?

The chart endpoint works fine from a residential browser and returned nothing
for all 120 funds from CI, so the question is not "does Yahoo have this data"
(it does) but "who answers a datacenter IP". This tries each candidate against
one Canadian TSX fund, one Cboe Canada fund and one US fund, and writes the
verdict to data/price-probe.json so it can be read without fighting the log
viewer.

Deliberately tiny: a handful of requests, seconds to run, so iterating on the
answer doesn't cost nine minutes a go.
"""
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

OUT = Path("data/price-probe.json")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
SAMPLES = [("HMAX", "TSX"), ("YTSL", "Cboe Canada"), ("SPYI", "US")]


def attempt(name: str, url: str, parse) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "en-CA,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", "replace")
            return {"source": name, "status": r.status, **parse(body)}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:160]
        except Exception:  # noqa: BLE001
            pass
        return {"source": name, "status": exc.code, "bars": 0, "note": detail}
    except Exception as exc:  # noqa: BLE001
        return {"source": name, "status": "error", "bars": 0, "note": str(exc)[:160]}


def parse_yahoo(body: str) -> dict:
    try:
        j = json.loads(body)
    except Exception:  # noqa: BLE001
        return {"bars": 0, "note": body[:160]}
    res = (j.get("chart") or {}).get("result")
    if not res:
        err = (j.get("chart") or {}).get("error")
        return {"bars": 0, "note": str(err)[:160]}
    ts = res[0].get("timestamp") or []
    return {"bars": len(ts), "currency": (res[0].get("meta") or {}).get("currency")}


def parse_stooq(body: str) -> dict:
    lines = [l for l in body.strip().splitlines() if l.strip()]
    if not lines or not lines[0].lower().startswith("date"):
        return {"bars": 0, "note": body[:120]}
    return {"bars": len(lines) - 1, "first": lines[1][:24] if len(lines) > 1 else ""}


def yahoo_with_crumb(symbol: str) -> dict:
    """Yahoo hands datacenter traffic a consent wall unless you carry a cookie
    and a matching crumb, so do the handshake first."""
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor()
    )
    opener.addheaders = [("User-Agent", UA), ("Accept", "*/*")]
    try:
        opener.open("https://fc.yahoo.com", timeout=20).read()
    except Exception:  # noqa: BLE001
        pass  # this call is expected to 404 — we only want the cookie it sets
    try:
        crumb = opener.open(
            "https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=20
        ).read().decode().strip()
    except Exception as exc:  # noqa: BLE001
        return {"source": "yahoo+crumb", "status": "crumb failed", "bars": 0,
                "note": str(exc)[:120]}
    if not crumb or len(crumb) > 40:
        return {"source": "yahoo+crumb", "status": "no crumb", "bars": 0,
                "note": crumb[:60]}
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{symbol}?range=1mo&interval=1d&crumb={urllib.parse.quote(crumb)}")
    try:
        body = opener.open(url, timeout=25).read().decode("utf-8", "replace")
        return {"source": "yahoo+crumb", "status": 200, **parse_yahoo(body)}
    except urllib.error.HTTPError as exc:
        return {"source": "yahoo+crumb", "status": exc.code, "bars": 0}
    except Exception as exc:  # noqa: BLE001
        return {"source": "yahoo+crumb", "status": "error", "bars": 0,
                "note": str(exc)[:120]}


import urllib.parse  # noqa: E402  (used by yahoo_with_crumb)


def main() -> None:
    report = {"samples": {}}
    for ticker, venue in SAMPLES:
        yahoo_sym = {"TSX": ticker + ".TO", "Cboe Canada": ticker + ".NE", "US": ticker}[venue]
        stooq_sym = {"TSX": ticker + ".ca", "Cboe Canada": ticker + ".ca", "US": ticker + ".us"}[venue]
        tries = [
            attempt("yahoo-q1",
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}?range=1mo&interval=1d",
                    parse_yahoo),
            attempt("yahoo-q2",
                    f"https://query2.finance.yahoo.com/v8/finance/chart/{yahoo_sym}?range=1mo&interval=1d",
                    parse_yahoo),
            yahoo_with_crumb(yahoo_sym),
            attempt("stooq",
                    f"https://stooq.com/q/d/l/?s={stooq_sym}&i=d",
                    parse_stooq),
        ]
        report["samples"][f"{ticker} ({venue})"] = tries
        for t in tries:
            print(f"{ticker:6} {t['source']:12} status={t.get('status')} bars={t.get('bars')} "
                  f"{t.get('note','')[:80]}")
        time.sleep(1.0)

    winners = sorted({t["source"] for v in report["samples"].values()
                      for t in v if t.get("bars")})
    report["sources_returning_data"] = winners
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print("\nSources that returned data from this runner:", winners or "NONE")


if __name__ == "__main__":
    main()
