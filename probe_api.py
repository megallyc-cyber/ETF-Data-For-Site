"""A fund that brought back distributions was not a failed fetch.

A fetch counted as successful only if holdings came back, so the funds whose
whole value is their distribution history looked like a failure every run.
The fresh data was then replaced by the previous record. Twenty-two funds
lost their yields that way, and would have lost them again tomorrow.
"""
import json, subprocess
from pathlib import Path

OLD1 = "            fund.fetched_ok = bool(fund.holdings)"
NEW1 = "            # Holdings are not the only thing worth fetching. A fund whose\n            # issuer publishes no holdings still has a price, a size and a\n            # distribution history; calling that a failed fetch meant carrying\n            # yesterday's record over today's and losing them.\n            fund.fetched_ok = bool(fund.holdings) or bool(fund.distributions)"
OLD2 = "    carried = [f.ticker for f in registry if f.stale and f.holdings]"
NEW2 = "    carried = [f.ticker for f in registry\n               if f.stale and (f.holdings or f.distributions)]"

p = Path("scraper.py")
t = p.read_text()
report = {}

if OLD1 in t:
    t = t.replace(OLD1, NEW1)
    report["fetchTest"] = "counts distributions too"
else:
    report["fetchTest"] = "anchor missing"

if OLD2 in t:
    t = t.replace(OLD2, NEW2)
    report["carriedReport"] = "matches the new test"
else:
    report["carriedReport"] = "anchor missing"

p.write_text(t)

import ast
try:
    ast.parse(t)
    report["scraperParses"] = True
except SyntaxError as exc:
    report["scraperParses"] = False
    report["syntaxError"] = str(exc)[:120]

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "A fund that brought back distributions was not a failed fetch"], check=False)
subprocess.run(["git", "push"], check=False)