"""One name for one place.

The nav said "Social" while the card and the page itself said "Social
Hub". Two names for the same room reads like two rooms.
"""
import json, subprocess
from pathlib import Path

PAGES = ["funds", "compare", "learn", "portfolio", "portfolio-builder",
         "backtest", "membership", "account", "fund", "tour",
         "privacy", "terms", "social", "social/post", "social/u",
         "social/admin", "social/admin/members"]

report = {"renamed": [], "skipped": []}

OLD = "<a href=\"/social\">Social</a>"
OLD_ACTIVE = "<a class=\"active\" href=\"/social\">Social</a>"
NEW = "<a href=\"/social\">Social Hub</a>"
NEW_ACTIVE = "<a class=\"active\" href=\"/social\">Social Hub</a>"

targets = [Path(p) / "index.html" for p in PAGES] + [Path("index.html")]
for f in targets:
    if not f.exists():
        report["skipped"].append(str(f) + ": missing")
        continue
    t = f.read_text()
    before = t
    t = t.replace(OLD_ACTIVE, NEW_ACTIVE).replace(OLD, NEW)
    if t != before:
        f.write_text(t)
        report["renamed"].append(str(f))
    else:
        report["skipped"].append(str(f) + ": nothing to rename")

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "One name for one place: Social Hub"], check=False)
subprocess.run(["git", "push"], check=False)