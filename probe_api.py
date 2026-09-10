"""Point the signposts at the new addresses.

A canonical tag naming the old .html address tells Google the old page
is the real one, which is worse than not moving at all. My first attempt
used a regex that over-escaped and matched nothing; plain replacement
cannot go wrong the same way.
"""
import json, subprocess
from datetime import date
from pathlib import Path

PAGES = ["funds", "compare", "learn", "portfolio", "portfolio-builder",
         "backtest", "membership", "account", "fund", "tour",
         "privacy", "terms"]

report = {"pages": [], "sitemap": None}


def clean(text):
    n = 0
    for p in PAGES:
        old = "https://licentia.ca/" + p + ".html"
        new = "https://licentia.ca/" + p
        n += text.count(old)
        text = text.replace(old, new)
    old_home = "https://licentia.ca/index.html"
    n += text.count(old_home)
    text = text.replace(old_home, "https://licentia.ca/")
    return text, n


targets = [Path(p) / "index.html" for p in PAGES] + [Path("index.html")]
for f in targets:
    if not f.exists():
        continue
    text, n = clean(f.read_text())
    if n:
        f.write_text(text)
        report["pages"].append(str(f) + " (" + str(n) + ")")

sm = Path("sitemap.xml")
if sm.exists():
    text, n = clean(sm.read_text())
    # every page moved today, so say so
    import re
    text = re.sub("<lastmod>[^<]*</lastmod>",
                  "<lastmod>" + date.today().isoformat() + "</lastmod>", text)
    sm.write_text(text)
    report["sitemap"] = str(n) + " urls rewritten"

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "Canonicals and sitemap name the new addresses"], check=False)
subprocess.run(["git", "push"], check=False)