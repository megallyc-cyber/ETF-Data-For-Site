"""Point the signposts at the new addresses.

The pages moved but their canonical tags still name the old .html
address, which tells Google the old one is the real page — the exact
opposite of what we want, and worse than leaving them alone. The
sitemap lists the old addresses too.
"""
import json, re, subprocess
from pathlib import Path

PAGES = ["funds", "compare", "learn", "portfolio", "portfolio-builder",
         "backtest", "membership", "account", "fund", "tour",
         "privacy", "terms"]

report = {"canonicals": [], "sitemap": None, "og": []}

def clean(html):
    n = 0
    for p in PAGES:
        # canonical, og:url and anything else naming the old address
        html, k = re.subn(r"https://licentia\\.ca/" + p + r"\\.html", 
                          "https://licentia.ca/" + p, html)
        n += k
    html, k = re.subn(r"https://licentia\\.ca/index\\.html", "https://licentia.ca/", html)
    n += k
    return html, n

for p in PAGES:
    f = Path(p) / "index.html"
    if not f.exists():
        continue
    html, n = clean(f.read_text())
    if n:
        f.write_text(html)
        report["canonicals"].append(p + " (" + str(n) + " urls)")

home = Path("index.html")
if home.exists():
    html, n = clean(home.read_text())
    if n:
        home.write_text(html)
        report["canonicals"].append("index.html (" + str(n) + " urls)")

sm = Path("sitemap.xml")
if sm.exists():
    text, n = clean(sm.read_text())
    # a moved page should carry today as its last change
    from datetime import date
    text = re.sub(r"<lastmod>[^<]*</lastmod>",
                  "<lastmod>" + date.today().isoformat() + "</lastmod>", text)
    sm.write_text(text)
    report["sitemap"] = str(n) + " urls updated, lastmod refreshed"

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "Canonicals and sitemap name the new addresses"], check=False)
subprocess.run(["git", "push"], check=False)