"""Why does the price job resolve some tickers and not others?"""
import json
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path("data/api-probe.json")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def try_symbol(sym):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + sym + "?range=1mo&interval=1d")
    try:
        with urlopen(Request(url, headers=UA), timeout=30) as r:
            body = r.read().decode()
            code = r.status
    except Exception as exc:
        return {"error": type(exc).__name__ + ": " + str(exc)[:120]}
    try:
        data = json.loads(body)
    except Exception:
        return {"status": code, "unparsable": body[:120]}
    chart = data.get("chart") or {}
    if chart.get("error"):
        return {"status": code, "yahoo_error": str(chart["error"])[:120]}
    res = (chart.get("result") or [None])[0]
    if not res:
        return {"status": code, "no_result": True}
    quote = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    closes = [c for c in (quote.get("close") or []) if c is not None]
    return {"status": code, "bars": len(closes),
            "last": round(closes[-1], 4) if closes else None}


report = {}
cases = [("ZWP", "CAD"), ("ZWT", "CAD"), ("QQCC", "CAD"),
         ("CEPI", "US"), ("MSTY", "US"), ("HHL", "CAD")]
for ticker, region in cases:
    t = ticker.replace(".", "-")
    if region == "CAD":
        candidates = [t + ".TO", t + ".NE", t + ".V"]
    else:
        candidates = [t, t + ".TO", t + ".NE"]
    report[ticker] = {c: try_symbol(c) for c in candidates}

report["_files_present"] = {
    t: Path("data/prices/" + t + ".csv").exists()
    for t in ("ZWP", "ZWT", "QQCC", "CEPI", "MSTY", "HHL")
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))