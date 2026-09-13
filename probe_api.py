"""Every Social page asked for pro.js without a version.

The rest of the site stamps that address, so a new build is fetched. These
five did not, which means a browser keeps serving whatever copy it happened
to cache \u2014 the Admin entry was in the file on the server and simply never
ran. The stamping step rewrites any address it recognises, so giving them
one to recognise is enough.
"""
import json, subprocess
from pathlib import Path

PAGES = ["social/index.html", "social/post/index.html", "social/u/index.html",
         "social/admin/index.html", "social/admin/members/index.html"]

OLD = "<script src=\"/assets/pro.js\">"
NEW = "<script src=\"/assets/pro.js?v=1\">"

report = {"stamped": [], "skipped": []}
for name in PAGES:
    f = Path(name)
    if not f.exists():
        report["skipped"].append(name + ": missing")
        continue
    t = f.read_text()
    if OLD not in t:
        report["skipped"].append(name + ": nothing to stamp")
        continue
    f.write_text(t.replace(OLD, NEW))
    report["stamped"].append(name)

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "Let the Social pages pick up new builds of pro.js"], check=False)
subprocess.run(["git", "push"], check=False)