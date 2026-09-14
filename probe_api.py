"""Keep the crawler summary out of sight.

It is the same words the page shows once it renders, so it is not hidden
text in the deceptive sense \u2014 it is there for a crawler that arrives before
the scripts run. Clipped rather than display:none, so it is still read out.
"""
import json, subprocess
from pathlib import Path

p = Path("scraper.py")
t = p.read_text()
report = {}

Q = chr(34)
BS = chr(92)
old = BS + Q + "seo-summary" + BS + Q
new = (BS + Q + "seo-summary" + BS + Q
       + " style=" + BS + Q
       + "position:absolute;width:1px;height:1px;overflow:hidden;"
       + "clip:rect(0 0 0 0);white-space:nowrap"
       + BS + Q)
if old in t and "clip:rect" not in t:
    t = t.replace(old, new, 1)
    p.write_text(t)
    report["summary"] = "clipped"
elif "clip:rect" in t:
    report["summary"] = "already clipped"
else:
    report["summary"] = "marker still not found"

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "Keep the crawler summary out of sight"], check=False)
subprocess.run(["git", "push"], check=False)