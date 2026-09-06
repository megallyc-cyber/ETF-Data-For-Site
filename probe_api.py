"""Does the 10y range still work, and can the existing files be read?"""
import csv, json
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path("data/api-probe.json")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"}


def ask(sym, rng):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + sym + "?range=" + rng + "&interval=1d")
    try:
        with urlopen(Request(url, headers=UA), timeout=40) as r:
            data = json.loads(r.read().decode())
    except Exception as exc:
        return {"error": type(exc).__name__ + ": " + str(exc)[:100]}
    res = ((data.get("chart") or {}).get("result") or [None])[0]
    if not res:
        err = (data.get("chart") or {}).get("error")
        return {"no_result": True, "yahoo_error": str(err)[:100]}
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    closes = [c for c in (q.get("close") or []) if c is not None]
    return {"bars": len(closes)}


report = {"ranges": {}}
for sym in ("ZWP.TO", "ZWB.TO", "MSTY"):
    report["ranges"][sym] = {r: ask(sym, r) for r in ("1mo", "10y", "max", "5y")}

# can the files already in the repo be read by the current parser?
sample = {}
for t in ("ZWB", "MSTY"):
    p = Path("data/prices/" + t + ".csv")
    if not p.exists():
        sample[t] = "missing"
        continue
    with p.open() as fh:
        rd = csv.DictReader(fh)
        rows = list(rd)
    sample[t] = {"columns": rd.fieldnames, "rows": len(rows),
                 "last": rows[-1] if rows else None}
report["existing_files"] = sample

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))