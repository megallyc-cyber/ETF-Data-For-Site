"""Which free price source will actually serve a GitHub runner?

Yahoo now refuses every request from Actions: 126 refusals in the last
run, no bars written, 17 tickers reached in forty minutes. Tuning the
politeness will not fix a block, so find a source that answers.
"""
import json, os
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path("data/api-probe.json")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"}


def get(url, headers=None):
    try:
        with urlopen(Request(url, headers=headers or UA), timeout=45) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as exc:
        return None, type(exc).__name__ + ": " + str(exc)[:110]


def stooq(sym):
    code, body = get("https://stooq.com/q/d/l/?s=" + sym + "&i=d")
    rows = [ln for ln in body.splitlines() if ln and ln[:1].isdigit()]
    return {"status": code, "rows": len(rows),
            "last": rows[-1][:24] if rows else body[:70]}


def yahoo(sym, host):
    code, body = get("https://" + host + "/v8/finance/chart/" + sym
                     + "?range=1mo&interval=1d")
    if code != 200:
        return {"status": code, "note": body[:70]}
    try:
        d = json.loads(body)
        res = ((d.get("chart") or {}).get("result") or [None])[0]
        q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
        closes = [c for c in (q.get("close") or []) if c is not None]
        return {"status": code, "bars": len(closes)}
    except Exception as exc:
        return {"status": code, "parse": str(exc)[:60]}


report = {}
# a Canadian listing and a US one, through each candidate source
report["stooq"] = {
    "HDIV.ca": stooq("hdiv.ca"),
    "ZWP.ca": stooq("zwp.ca"),
    "MSTY.us": stooq("msty.us"),
    "CEPI.us": stooq("cepi.us"),
}
report["yahoo_query1"] = {"HDIV.TO": yahoo("HDIV.TO", "query1.finance.yahoo.com")}
report["yahoo_query2"] = {"HDIV.TO": yahoo("HDIV.TO", "query2.finance.yahoo.com")}

td = os.environ.get("TWELVEDATA_API_KEY", "")
if td:
    code, body = get("https://api.twelvedata.com/time_series?symbol=HDIV:TSX"
                     + "&interval=1day&outputsize=5&apikey=" + td)
    report["twelvedata_tsx_suffix"] = {"status": code, "head": body[:120]}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))