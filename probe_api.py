"""Do the Canadian listings exist at the fallback source?

Sixty-three funds still have no calculated yield and almost all are
Canadian. Before changing any parser, find out whether the pages are there
at all, and under which path.
"""
import json, re, urllib.request
from pathlib import Path
from datetime import datetime, timezone

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TAGS = re.compile(r"<[^>]+>")
TODAY = datetime.now(timezone.utc).date().isoformat()

def cells_of(row):
    parts = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
    return [TAGS.sub("", p).replace("&nbsp;", " ").strip() for p in parts]

def look(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=35) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return str(exc)[:40]
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.S | re.I)
    if not tables:
        return "no table"
    big = max(tables, key=len)
    rows = [cells_of(r) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", big, re.S | re.I)]
    paid = [r for r in rows[1:] if len(r) > 2 and r[0] <= TODAY]
    return str(len(paid)) + " paid rows"

report = {}
for t in ["QQCC", "USCC", "HGY", "BCCL", "MPAY", "CNCC", "BRKY", "YUNH", "TY"]:
    report[t] = {
        "tsx": look("https://dividendhistory.org/payout/tsx/" + t + "/"),
        "plain": look("https://dividendhistory.org/payout/" + t + "/"),
    }

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))