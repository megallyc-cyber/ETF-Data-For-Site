"""What the distribution table actually looks like now.

The parser reads the third cell of each row. If that source changed its
columns, every fund depending on it loses its history and its yield with
it. Print the real cells. No bs4 on this runner, so read it with a regex.
"""
import json, re, urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

TAGS = re.compile(r"<[^>]+>")

def cells_of(row_html):
    parts = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S | re.I)
    return [TAGS.sub("", p).replace("&nbsp;", " ").strip() for p in parts]

def look(ticker):
    url = "https://dividendhistory.org/payout/" + ticker + "/"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        html = r.read().decode("utf-8", "replace")
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.S | re.I)
    ids = re.findall(r"<table[^>]*id=[\"\']([^\"\']+)", html, re.I)
    out = {"tableCount": len(tables), "tableIds": ids}
    if not tables:
        return out
    # the biggest table is the history
    big = max(tables, key=len)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", big, re.S | re.I)
    out["rowCount"] = len(rows)
    out["sample"] = [cells_of(r) for r in rows[:5]]
    return out

report = {}
for t in ["HYGW", "JEPI"]:
    try:
        report[t] = look(t)
    except Exception as exc:  # noqa: BLE001
        report[t] = {"error": str(exc)[:130]}

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))