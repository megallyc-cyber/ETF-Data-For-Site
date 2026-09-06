"""Diagnostic: can the runner reach BMO, and are the price files there?

The scrape reports success while nothing on the site changes, and the job log
will not render in the tooling available, so this writes what it finds to a
file in the repo where it can actually be read. Standard library only: this
workflow installs nothing.
"""
import json
import traceback
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path("data/api-probe.json")
BMO = "https://df.bmogam.com/api/graphql/etf-funds-production"
QUERY = ("query T($locale: String, $entityId: String) {"
         "  webProfiles(locale: $locale, entityId: $entityId, take: 1) {"
         "    fundName"
         "    fund { portfolios(sortDirection: \"D\", take: 1) {"
         "      kb2Holdings { allocation holding ticker } } }"
         "  } }")

report = {}

for ticker in ("ZWP", "ZWT", "ZWB"):
    entry = {}
    try:
        body = json.dumps({"query": QUERY,
                           "variables": {"locale": "en-US",
                                         "entityId": ticker + "-a",
                                         "env": "production"}}).encode()
        req = Request(BMO, data=body, method="POST",
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            entry["status"] = resp.status
        entry["bytes"] = len(raw)
        data = json.loads(raw)
        profs = (data.get("data") or {}).get("webProfiles") or []
        entry["profiles"] = len(profs)
        if profs:
            entry["name"] = profs[0].get("fundName")
            ports = (profs[0].get("fund") or {}).get("portfolios") or []
            rows = (ports[0].get("kb2Holdings") if ports else []) or []
            entry["rows"] = len(rows)
            entry["sample"] = [[h.get("ticker"), h.get("allocation")] for h in rows[:3]]
        else:
            entry["body_head"] = raw[:200]
    except Exception as exc:  # noqa: BLE001
        entry["error"] = type(exc).__name__ + ": " + str(exc)
        entry["trace"] = traceback.format_exc()[-300:]
    report[ticker] = entry

report["price_files"] = {
    t: Path("data/prices/" + t + ".csv").exists()
    for t in ("MSTY", "QQCC", "ZWT", "CEPI", "HHL")
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))