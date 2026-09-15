"""The last nine funds without a yield.

HYGW, SPYT and NVII all came good from the same fallback, so the source and
the parser work. Ask what these nine actually return before changing
anything: whether the page exists, and whether it has paid rows on it.
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
        with urllib.request.urlopen(req, timeout=40) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:90]}
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.S | re.I)
    if not tables:
        return {"rows": 0, "note": "no table"}
    big = max(tables, key=len)
    rows = [cells_of(r) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", big, re.S | re.I)]
    paid = [r for r in rows[1:]
            if len(r) > 3 and r[0] <= TODAY
            and "unconfirm" not in r[3].lower() and "estimat" not in r[3].lower()]
    return {"rows": len(rows) - 1, "paidRows": len(paid),
            "firstPaid": paid[0] if paid else None}

report = {}
for t in ["DACL", "FEPI", "LQDW", "ISPY", "ATCL", "AIPI", "JEPY", "BALI", "TLTW"]:
    report[t] = {"plain": look("https://dividendhistory.org/payout/" + t + "/")}

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))