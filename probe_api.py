"""Diagnostic: can the runner reach BMO, and does the scraper path work?

The scrape reports success while the site never changes, and the job log will
not render in the tooling available, so this writes its findings to a file in
the repo where they can actually be read.
"""
import json
import traceback
from pathlib import Path

import requests

OUT = Path("data/api-probe.json")
BMO = "https://df.bmogam.com/api/graphql/etf-funds-production"
QUERY = """query T($locale: String, $entityId: String) {
  webProfiles(locale: $locale, entityId: $entityId, take: 1) {
    fundName
    fund { portfolios(sortDirection: "D", take: 1) { kb2Holdings { allocation holding ticker } } }
  }
}"""

report = {}

for ticker in ("ZWP", "ZWT", "ZWB"):
    entry = {}
    try:
        r = requests.post(BMO, timeout=60,
                          headers={"Content-Type": "application/json"},
                          json={"query": QUERY,
                                "variables": {"locale": "en-US",
                                              "entityId": ticker + "-a",
                                              "env": "production"}})
        entry["status"] = r.status_code
        entry["bytes"] = len(r.text)
        data = r.json()
        profs = (data.get("data") or {}).get("webProfiles") or []
        entry["profiles"] = len(profs)
        if profs:
            entry["name"] = profs[0].get("fundName")
            ports = (profs[0].get("fund") or {}).get("portfolios") or []
            rows = ports[0].get("kb2Holdings") if ports else []
            entry["rows"] = len(rows or [])
            entry["sample"] = [(h.get("ticker"), h.get("allocation")) for h in (rows or [])[:3]]
        else:
            entry["body_head"] = r.text[:200]
    except Exception as exc:  # noqa: BLE001
        entry["error"] = f"{type(exc).__name__}: {exc}"
        entry["trace"] = traceback.format_exc()[-400:]
    report[ticker] = entry

# can the runner see the price files the scraper depends on?
report["price_files"] = {
    t: Path(f"data/prices/{t}.csv").exists()
    for t in ("MSTY", "QQCC", "ZWT", "CEPI", "HHL")
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))