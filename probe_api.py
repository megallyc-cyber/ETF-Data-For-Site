"""Two things my own link rewrite broke.

1. The nav grouping matches a link by its file name. The rewrite turned
   learn.html into /learn, so nothing matched and the bar fell back to
   nine flat links.

2. Price series are fetched as data/prices/X.csv, which is relative.
   From /backtest/ that now resolves to /backtest/data/ and 404s, so
   nothing can be charted even though the files finally exist.
"""
import json, subprocess
from pathlib import Path

PAGES = ["funds", "compare", "learn", "portfolio", "portfolio-builder",
         "backtest", "membership", "account", "fund", "tour",
         "privacy", "terms"]

report = {"dataPaths": [], "nav": None}

# 1. the grouping should compare against what the links now say
pro = Path("assets/pro.js")
if pro.exists():
    t = pro.read_text()
    old = 'const file = (a.getAttribute("href") || "").split("/").pop().split("?")[0];'
    new = ('// a link may be written as /learn or as learn.html; compare on the\n'
           '      // bare name so either shape groups correctly\n'
           '      const file = (a.getAttribute("href") || "")\n'
           '        .split("?")[0].replace(/\\.html$/, "").split("/").filter(Boolean).pop() || "";')
    if old in t:
        t = t.replace(old, new)
        # and the lists themselves lose the extension
        for p in PAGES:
            t = t.replace("'/" + p + "'", "'" + p + "'")
        pro.write_text(t)
        report["nav"] = "matcher and lists normalised"
    else:
        report["nav"] = "matcher line not found"

# 2. data paths must be absolute now that pages sit in folders
targets = [Path(p) / "index.html" for p in PAGES]
targets += [Path("index.html"), Path("assets/pro.js")]
for f in targets:
    if not f.exists():
        continue
    text = f.read_text()
    n = 0
    for quote in ('"', "'", "`"):
        for prefix in ("data/prices/", "data/"):
            old = quote + prefix
            new = quote + "/" + prefix
            n += text.count(old)
            text = text.replace(old, new)
    if n:
        f.write_text(text)
        report["dataPaths"].append(str(f) + " (" + str(n) + ")")

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "Restore the grouped nav and let the charts find their prices"], check=False)
subprocess.run(["git", "push"], check=False)