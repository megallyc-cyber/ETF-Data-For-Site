"""Define the two delays my last change started using.

The guard that was meant to avoid adding them twice saw the names in the
code I had just inserted and skipped the definitions. The file still parses,
because a missing name is only found when the line runs \u2014 which would have
been on the first fallback of the next scrape.
"""
import json, subprocess
from pathlib import Path

p = Path("scraper.py")
t = p.read_text()
report = {}

anchor = "DELAY_BETWEEN_REQUESTS = 1.5  # be polite, avoid hammering issuer sites"
defined = "DH_DELAY = " in t

if defined:
    report["state"] = "already defined"
elif anchor in t:
    adds = (anchor + chr(10)
            + "DH_DELAY = 4.0     # the fallback is one site asked a hundred times" + chr(10)
            + "DH_BACKOFF = 12.0  # and it needs a real pause once it has refused")
    t = t.replace(anchor, adds)
    p.write_text(t)
    report["state"] = "defined"
else:
    report["state"] = "anchor missing"

# prove both names exist before they are used
report["dhDelayDefined"] = "DH_DELAY = " in t
report["dhBackoffDefined"] = "DH_BACKOFF = " in t
report["usedInLoop"] = "time.sleep(DH_DELAY)" in t

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
subprocess.run(["git", "commit", "-m", "Define the delays my last change started using"], check=False)
subprocess.run(["git", "push"], check=False)