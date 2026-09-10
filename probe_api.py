"""Give every page a clean address, once, across the whole site.

funds.html becomes funds/index.html, served at /funds. Doing this by
hand across twelve pages and every link between them is how links get
missed, so it happens here in one pass with a report at the end.

The old addresses stay as redirect stubs: licentia.ca/funds.html is what
Google has indexed today, and dropping it would throw that away.
"""
import json, re, subprocess
from pathlib import Path

PAGES = ["funds", "compare", "learn", "portfolio", "portfolio-builder",
         "backtest", "membership", "account", "fund", "tour",
         "privacy", "terms"]

report = {"converted": [], "stubs": [], "skipped": [], "linksRewritten": 0}


def rooted(html: str) -> str:
    """Paths that work from any depth."""
    n = 0
    # assets and data must be absolute once a page sits in a folder
    html, k = re.subn(r'(src|href)="(assets/|data/)', r'\1="/\2', html)
    n += k
    # internal page links lose the extension
    for p in PAGES:
        html, k = re.subn(r'(src|href)="' + p + r'\.html"', r'\1="/' + p + '"', html)
        n += k
        html, k = re.subn(r'(src|href)="' + p + r'\.html\?', r'\1="/' + p + '?', html)
        n += k
    html, k = re.subn(r'(src|href)="index\.html"', r'\1="/"', html)
    n += k
    html, k = re.subn(r'(src|href)="index\.html\?', r'\1="/?', html)
    n += k
    return html, n


def stub(page: str) -> str:
    """The old address, pointing at the new one."""
    url = "https://licentia.ca/" + page
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"UTF-8\">\n"
        '<link rel="canonical" href="' + url + '">\n'
        '<meta http-equiv="refresh" content="0; url=' + url + '">\n'
        '<meta name="robots" content="noindex, follow">\n'
        "<title>Moved</title>\n</head>\n<body>\n"
        '<p>This page now lives at <a href="' + url + '">' + url + '</a>.</p>\n'
        "</body>\n</html>\n")


for page in PAGES:
    src = Path(page + ".html")
    if not src.exists():
        report["skipped"].append(page + ": no such file")
        continue
    html = src.read_text()
    if "http-equiv=\"refresh\"" in html:
        report["skipped"].append(page + ": already a stub")
        continue
    converted, n = rooted(html)
    report["linksRewritten"] += n
    folder = Path(page)
    folder.mkdir(exist_ok=True)
    (folder / "index.html").write_text(converted)
    report["converted"].append(page + "/index.html (" + str(n) + " paths)")
    src.write_text(stub(page))
    report["stubs"].append(page + ".html")

# the homepage stays at the root but its links still need rewriting
home = Path("index.html")
if home.exists():
    html, n = rooted(home.read_text())
    home.write_text(html)
    report["linksRewritten"] += n
    report["converted"].append("index.html stays at / (" + str(n) + " paths)")

# and the shared script writes its own nav links
pro = Path("assets/pro.js")
if pro.exists():
    t = pro.read_text()
    for p in PAGES:
        t = t.replace("'" + p + ".html'", "'/" + p + "'")
        t = t.replace('"' + p + '.html"', '"/' + p + '"')
    t = t.replace("'index.html'", "'/'").replace('"index.html"', '"/"')
    pro.write_text(t)
    report["converted"].append("assets/pro.js nav links")

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m",
                "Clean addresses: /funds rather than /funds.html"], check=False)
subprocess.run(["git", "push"], check=False)