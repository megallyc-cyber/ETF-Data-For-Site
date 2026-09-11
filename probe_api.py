"""Give every fund a page of its own that a search engine can read.

/fund?t=HDIV is one address to Google with the title "Fund detail", and
the real content only appears once scripts have run. Someone searching
"HDIV ETF" finds nothing of ours. This writes a real file per fund with
the title, description and figures already in the HTML, and lets the
existing interactive page load on top of it.
"""
import html as _html
import json, re, subprocess
from pathlib import Path

report = {"patched": [], "note": None}

# 1. the interactive page must accept a ticker given to it, not only one
#    read from a query string, since the new pages have no query string.
f = Path("fund/index.html")
if f.exists():
    t = f.read_text()
    old = 'var t = (new URLSearchParams(location.search).get(\'t\') || \'\').toUpperCase();'
    new = ('// a generated page names its fund directly; the query string still\n'
           '  // works for links written by hand\n'
           '  var t = (window.__TICKER ||\n'
           '    new URLSearchParams(location.search).get("t") || "").toUpperCase();')
    if old in t:
        t = t.replace(old, new)
        f.write_text(t)
        report["patched"].append("fund/index.html accepts a named ticker")
    elif "window.__TICKER" in t:
        report["patched"].append("fund/index.html already accepts one")
    else:
        report["note"] = "could not find the ticker line in fund/index.html"

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "A fund page can be told which fund it is"], check=False)
subprocess.run(["git", "push"], check=False)