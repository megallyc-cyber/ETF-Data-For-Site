"""The links built in JavaScript were missed by the move.

The first pass rewrote href="fund.html" in the markup, but most links on
this site are assembled in script as strings like fund.html?t=DIVO.
Those are relative, and now that the page lives at /funds/ they resolve
to /funds/fund.html and fail. Every fund page was unreachable from the
directory because of it.
"""
import json, subprocess
from pathlib import Path

PAGES = ["funds", "compare", "learn", "portfolio", "portfolio-builder",
         "backtest", "membership", "account", "fund", "tour",
         "privacy", "terms", "index"]

report = {"files": [], "total": 0}


def fix(text):
    n = 0
    for p in PAGES:
        target = "/" if p == "index" else "/" + p
        for quote in ('"', "'", "`"):
            # a link with a query string, e.g. fund.html?t=
            old = quote + p + ".html?"
            new = quote + target + "?"
            n += text.count(old)
            text = text.replace(old, new)
            # and a bare one, e.g. "funds.html"
            old2 = quote + p + ".html" + quote
            new2 = quote + target + quote
            n += text.count(old2)
            text = text.replace(old2, new2)
    return text, n


targets = [Path(p) / "index.html" for p in PAGES if p != "index"]
targets += [Path("index.html"), Path("404.html"), Path("assets/pro.js")]
for f in targets:
    if not f.exists():
        continue
    text, n = fix(f.read_text())
    if n:
        f.write_text(text)
        report["files"].append(str(f) + " (" + str(n) + ")")
        report["total"] += n

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "Fix the links built in script, which the move missed"], check=False)
subprocess.run(["git", "push"], check=False)