"""Finish the fund pages: a canonical, the sitemap, and links that reach them."""
import json, re, subprocess
from pathlib import Path

report = {}

# 1. the generated pages need a canonical of their own. The template has
#    none, and without one Google may treat /fund/HDIV and the old query
#    string as the same page, which wastes the whole exercise.
s = Path("scraper.py").read_text()
old = '        if \'rel="canonical"\' in page:'
if old in s:
    new = ('        page = re.sub(r\'<link rel="canonical"[^>]*>\', "", page)\n'
           '        page = page.replace("</head>",\n'
           '            \'<link rel="canonical" href="\' + url + \'">\\n</head>\', 1)\n'
           '        if False:')
    s = s.replace(old, new)
    Path("scraper.py").write_text(s)
    report["canonical"] = "always written"
else:
    report["canonical"] = "anchor missing"

# 2. the directory should link straight at the new pages
f = Path("funds/index.html")
if f.exists():
    t = f.read_text()
    o = "card.href = '/fund?t=' + encodeURIComponent(ticker);"
    n = ("// link at the page written for this fund, so a crawler can reach it\n"
         "  card.href = '/fund/' + encodeURIComponent(ticker);")
    if o in t:
        t = t.replace(o, n)
        f.write_text(t)
        report["directory"] = "links to /fund/TICKER"
    else:
        report["directory"] = "anchor missing"

# 3. Learn had no heading at all, which is a basic thing to be missing
l = Path("learn/index.html")
if l.exists():
    t = l.read_text()
    if "<h1" not in t:
        t = re.sub(r"(<main[^>]*>)",
                   r"\\1\n  <h1>How covered call and income ETFs actually work</h1>",
                   t, count=1)
        l.write_text(t)
        report["learn"] = "given a heading"
    else:
        report["learn"] = "already had one"

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "Canonical, directory links and a heading for Learn"], check=False)
subprocess.run(["git", "push"], check=False)