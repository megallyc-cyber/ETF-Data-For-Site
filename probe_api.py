"""Never come back from a scrape with less than we started with.

CPCC was showing a 6.85% yield and no distributions at all: the figure had
survived from an earlier run while the payments behind it were wiped by a
later one. A source refusing us today says nothing about whether those
payments happened, so keep what we had and try again tomorrow.
"""
import json, subprocess
from pathlib import Path

OLD = "                prev = previous.get(fund.ticker) or {}\n                if prev.get(\"holdings\"):\n                    fund.holdings = prev[\"holdings\"]\n                    fund.stale = True"
NEW = "                prev = previous.get(fund.ticker) or {}\n                if prev.get(\"holdings\"):\n                    fund.holdings = prev[\"holdings\"]\n                    fund.stale = True\n                # Never come back with less than we already had. A source that\n                # refuses us today is not evidence that yesterday's payments\n                # stopped existing, and dropping them takes the yield with them.\n                if not fund.distributions and prev.get(\"distributions\"):\n                    fund.distributions = prev[\"distributions\"]\n                    fund.stale = True"

p = Path("scraper.py")
t = p.read_text()
report = {}

if OLD in t:
    t = t.replace(OLD, NEW)
    report["keepDistributions"] = "carried forward when a fetch comes back empty"
else:
    report["keepDistributions"] = "anchor missing"

# the long waits did not help and cost two and a half hours; put them back
t = t.replace("DH_DELAY = 4.0", "DH_DELAY = 2.0")
t = t.replace("DH_BACKOFF = 12.0", "DH_BACKOFF = 8.0")
report["delays"] = "eased back"

p.write_text(t)

import ast
try:
    ast.parse(t)
    report["parses"] = True
except SyntaxError as exc:
    report["parses"] = False
    report["error"] = str(exc)[:110]

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "A scrape must never come back with less than it started with"], check=False)
subprocess.run(["git", "push"], check=False)