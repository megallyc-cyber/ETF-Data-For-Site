"""Two things I left half done.

1. The heading I added to Learn had no styling of its own, so it sat
   against the left edge in the wrong face, above the real title. The
   page already says what it is; that sentence should be the heading.

2. Social was in the nav on the social pages only. The bar is written out
   in every page separately, so a new entry has to be added to each one or
   it appears to vanish as you move around.
"""
import json, subprocess
from pathlib import Path

PAGES = ["funds", "compare", "learn", "portfolio", "portfolio-builder",
         "backtest", "membership", "account", "fund", "tour",
         "privacy", "terms"]

report = {"socialAdded": [], "learn": None, "skipped": []}

lp = Path("learn/index.html")
if lp.exists():
    t = lp.read_text()
    stray = "      <h1>How covered call and income ETFs actually work</h1>\n"
    if stray in t:
        t = t.replace(stray, "")
        t = t.replace("<h2>The whole idea, in about a minute..</h2>",
                      "<h1>How covered call and income ETFs work</h1>")
        lp.write_text(t)
        report["learn"] = "heading is the page title again"
    else:
        report["learn"] = "stray heading not found"

LINK = "<a href=\"/social\">Social</a>"
ANCHOR = "<a href=\"/backtest\">Backtesting</a>"

targets = [Path(p) / "index.html" for p in PAGES] + [Path("index.html")]
for f in targets:
    if not f.exists():
        report["skipped"].append(str(f) + ": missing")
        continue
    t = f.read_text()
    if LINK in t:
        report["skipped"].append(str(f) + ": already there")
        continue
    if ANCHOR not in t:
        report["skipped"].append(str(f) + ": no nav anchor")
        continue
    i = t.index(ANCHOR) + len(ANCHOR)
    t = t[:i] + "\n    " + LINK + t[i:]
    f.write_text(t)
    report["socialAdded"].append(str(f))

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "Social in every nav, and Learn gets its title back"], check=False)
subprocess.run(["git", "push"], check=False)