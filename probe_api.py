"""Replay the exact BMO parse and report where rows are lost."""
import json, traceback
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path("data/api-probe.json")
BMO = "https://df.bmogam.com/api/graphql/etf-funds-production"
Q = ("query T($locale: String, $entityId: String) {"
     "  webProfiles(locale: $locale, entityId: $entityId, take: 1) {"
     "    fundName"
     "    fund { portfolios(sortDirection: \"D\", take: 1) {"
     "      kb2Holdings { allocation holding ticker } } }"
     "  } }")

report = {}
for tic in ("ZWP", "ZWT"):
    e = {}
    try:
        body = json.dumps({"query": Q, "variables": {"locale": "en-US",
               "entityId": tic + "-a", "env": "production"}}).encode()
        req = Request(BMO, data=body, method="POST",
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode())
        profs = (data.get("data") or {}).get("webProfiles") or []
        ports = ((profs[0].get("fund") or {}).get("portfolios") or []) if profs else []
        rows = (ports[0].get("kb2Holdings") if ports else []) or []
        e["rows"] = len(rows)
        kept = {}
        drop = {"no_alloc": 0, "no_label": 0, "cash_or_option": 0, "not_positive": 0}
        for row in rows:
            sym = (row.get("ticker") or "").strip()
            name = (row.get("holding") or "").strip()
            alloc = row.get("allocation")
            if alloc is None:
                drop["no_alloc"] += 1; continue
            label = sym or name
            if not label:
                drop["no_label"] += 1; continue
            if "CALL OPTION" in name.upper() or name.lower().startswith("cash"):
                drop["cash_or_option"] += 1; continue
            w = float(alloc) * 100
            if w <= 0:
                drop["not_positive"] += 1; continue
            kept[label[:44]] = round(w, 2)
        e["kept"] = len(kept)
        e["dropped"] = drop
        e["sample_kept"] = list(kept.items())[:5]
        e["sample_raw"] = [[x.get("ticker"), x.get("holding"), x.get("allocation")] for x in rows[:6]]
    except Exception as exc:
        e["error"] = type(exc).__name__ + ": " + str(exc)
        e["trace"] = traceback.format_exc()[-300:]
    report[tic] = e

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))