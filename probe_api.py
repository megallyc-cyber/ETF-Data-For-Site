"""Stop the fallback being throttled during a full run.

Every one of these funds works when scraped on its own and comes back empty
from the nightly pass. The difference is volume: a hundred requests to the
same source, a second and a half apart. Slow the fallback down and retry a
refusal once.
"""
import json, subprocess
from pathlib import Path

OLD = "    for url in dividendhistory_urls(fund):\n        try:\n            log.info(\"  -> distributions fallback %s\", url)\n            html = fetch(url)\n            time.sleep(DELAY_BETWEEN_REQUESTS)\n            rows = parse_dividendhistory(html)\n            if rows:\n                log.info(\"  -> %d distributions from %s, latest %s\",\n                         len(rows), DH_ATTRIBUTION, rows[0][\"ex_date\"])\n                return rows\n            log.info(\"  -> no usable rows at %s\", url)\n        except Exception as exc:  # noqa: BLE001\n            log.info(\"  -> %s: %s\", url, exc)"
NEW = "    # One fund at a time this source answers happily. A full run asks it a\n    # hundred times in a few minutes and it starts refusing, which is why the\n    # funds that work when re-run alone come back empty from the nightly pass.\n    # Wait longer between calls, and give a refusal a second chance.\n    for url in dividendhistory_urls(fund):\n        for attempt in (1, 2):\n            try:\n                log.info(\"  -> distributions fallback %s\", url)\n                html = fetch(url)\n                time.sleep(DH_DELAY)\n                rows = parse_dividendhistory(html)\n                if rows:\n                    log.info(\"  -> %d distributions from %s, latest %s\",\n                             len(rows), DH_ATTRIBUTION, rows[0][\"ex_date\"])\n                    return rows\n                log.info(\"  -> no usable rows at %s\", url)\n                break            # the page loaded and had nothing; another try will not help\n            except Exception as exc:  # noqa: BLE001\n                log.info(\"  -> %s (attempt %d): %s\", url, attempt, exc)\n                if attempt == 1:\n                    time.sleep(DH_BACKOFF)"

p = Path("scraper.py")
t = p.read_text()
report = {}

if OLD in t:
    t = t.replace(OLD, NEW)
    report["fallbackLoop"] = "slowed, with one retry"
else:
    report["fallbackLoop"] = "anchor missing"

anchor = "DELAY_BETWEEN_REQUESTS = 1.5  # be polite, avoid hammering issuer sites"
adds = (anchor + chr(10)
        + "DH_DELAY = 4.0   # the distribution fallback is one site asked many times" + chr(10)
        + "DH_BACKOFF = 12.0  # and it needs a real pause once it has refused")
if anchor in t and "DH_DELAY" not in t:
    t = t.replace(anchor, adds)
    report["delays"] = "added"
elif "DH_DELAY" in t:
    report["delays"] = "already there"
else:
    report["delays"] = "anchor missing"

p.write_text(t)

import ast
try:
    ast.parse(t)
    report["scraperParses"] = True
except SyntaxError as exc:
    report["scraperParses"] = False
    report["error"] = str(exc)[:120]

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "Do not let a full run get the fallback throttled"], check=False)
subprocess.run(["git", "push"], check=False)