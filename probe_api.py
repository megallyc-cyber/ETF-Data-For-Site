"""Which provider can actually serve our tickers, and on this plan?

Yahoo answers every request with 429 from the runner, so the price
files have not moved since August. Both keys are already in the repo
secrets from an earlier evaluation; find out what each covers before
rewriting the job around one of them.
"""
import json, os
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path("data/api-probe.json")
TD = os.environ.get("TWELVEDATA_API_KEY", "")
FMP = os.environ.get("FMP_API_KEY", "")
UA = {"User-Agent": "Mozilla/5.0"}


def get(url):
    try:
        with urlopen(Request(url, headers=UA), timeout=40) as r:
            return r.status, r.read().decode()[:4000]
    except Exception as exc:
        return None, type(exc).__name__ + ": " + str(exc)[:120]


def twelve(sym):
    if not TD:
        return {"no_key": True}
    code, body = get("https://api.twelvedata.com/time_series?symbol=" + sym
                     + "&interval=1day&outputsize=30&apikey=" + TD)
    try:
        d = json.loads(body)
    except Exception:
        return {"status": code, "unparsable": body[:120]}
    if d.get("status") == "error":
        return {"status": code, "error": str(d.get("message"))[:140]}
    vals = d.get("values") or []
    return {"status": code, "bars": len(vals),
            "last": vals[0].get("close") if vals else None}


def fmp(sym):
    if not FMP:
        return {"no_key": True}
    code, body = get("https://financialmodelingprep.com/api/v3/historical-price-full/"
                     + sym + "?serietype=line&apikey=" + FMP)
    try:
        d = json.loads(body)
    except Exception:
        return {"status": code, "unparsable": body[:120]}
    if isinstance(d, dict) and d.get("Error Message"):
        return {"status": code, "error": str(d["Error Message"])[:140]}
    hist = (d or {}).get("historical") or []
    return {"status": code, "bars": len(hist),
            "last": hist[0].get("close") if hist else None}


report = {"keys": {"twelvedata": bool(TD), "fmp": bool(FMP)}}
# a Canadian listing, a US one, and one of each that is currently missing
for sym in ("ZWP.TO", "ZWB.TO", "QQCC.TO", "MSTY", "CEPI"):
    report[sym] = {"twelvedata": twelve(sym), "fmp": fmp(sym)}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))