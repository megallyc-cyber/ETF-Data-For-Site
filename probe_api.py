"""What the distribution table actually looks like now.

The parser reads the third cell of each row. If that source changed its
columns, every fund that depends on it would quietly lose its history \u2014
and its yield with it. Print the real cells rather than guess.
"""
import json, re, urllib.request
from pathlib import Path
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

def rows(ticker):
    url = "https://dividendhistory.org/payout/" + ticker + "/"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        html = r.read().decode("utf-8", "replace")
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="dividend-table") or soup.find("table")
    if not table:
        return {"error": "no table"}
    head = [c.get_text(" ", strip=True)
            for c in (table.find("tr").find_all(["th", "td"]) if table.find("tr") else [])]
    body = []
    for tr in table.find_all("tr")[1:5]:
        body.append([c.get_text(" ", strip=True) for c in tr.find_all("td")])
    return {"tableId": table.get("id"), "header": head, "firstRows": body}

report = {}
for t in ["HYGW", "JEPI", "TLTW"]:
    try:
        report[t] = rows(t)
    except Exception as exc:  # noqa: BLE001
        report[t] = {"error": str(exc)[:120]}

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))