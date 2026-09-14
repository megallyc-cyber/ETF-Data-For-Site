"""A fixed ?v=1 is not a cache buster.

I stamped the Social pages with a constant, so browsers kept the copy they
already had — the same fault I was trying to cure. Stamp them with a hash of
the file instead, so the address changes exactly when the file does.
"""
import hashlib, json, re, subprocess
from pathlib import Path

pro = Path("assets/pro.js")
stamp = hashlib.sha1(pro.read_bytes()).hexdigest()[:8] if pro.exists() else "1"

PAGES = ["social/index.html", "social/post/index.html", "social/u/index.html",
         "social/admin/index.html", "social/admin/members/index.html"]

report = {"stamp": stamp, "updated": [], "skipped": []}
for name in PAGES:
    f = Path(name)
    if not f.exists():
        report["skipped"].append(name)
        continue
    t = f.read_text()
    new = re.sub(r'/assets/pro\.js(\?v=[^"]*)?', "/assets/pro.js?v=" + stamp, t)
    if new != t:
        f.write_text(new)
        report["updated"].append(name)

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "Stamp with a hash, so the address changes when the file does"], check=False)
subprocess.run(["git", "push"], check=False)