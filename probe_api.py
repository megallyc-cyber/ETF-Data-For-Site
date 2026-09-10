"""Undo the redirect loop, and keep the old links working anyway.

GitHub Pages answers /funds with funds.html before it looks for
funds/index.html. The stub there redirected to /funds, which served the
stub again: every page became a loop. The stubs have to go.

Old addresses are carried by a custom 404 instead, which Pages serves
for anything it cannot find: it strips the .html and sends the reader on.
"""
import json, subprocess
from pathlib import Path

PAGES = ["funds", "compare", "learn", "portfolio", "portfolio-builder",
         "backtest", "membership", "account", "fund", "tour",
         "privacy", "terms"]

report = {"removedStubs": [], "kept": [], "notes": []}

for page in PAGES:
    stub = Path(page + ".html")
    folder = Path(page) / "index.html"
    if not folder.exists():
        report["notes"].append(page + ": no folder, stub left alone")
        continue
    if stub.exists():
        text = stub.read_text()
        if "http-equiv" in text and "refresh" in text:
            stub.unlink()
            report["removedStubs"].append(page + ".html")
        else:
            report["kept"].append(page + ".html (not a stub)")

NOT_FOUND = "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"UTF-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n<meta name=\"robots\" content=\"noindex, follow\">\n<title>That page has moved &mdash; Licentia</title>\n<link rel=\"stylesheet\" href=\"/assets/pro.css\">\n<style>\n  body{background:#F4F1E8; color:#1C2230; font-family:Inter,ui-sans-serif,sans-serif;\n    display:flex; align-items:center; justify-content:center; min-height:100vh;\n    margin:0; padding:24px; text-align:center;}\n  h1{font-family:Fraunces,serif; font-weight:400; font-size:30px; margin:0 0 10px;}\n  p{color:#4A5262; margin:0 0 18px;}\n  a{color:#1C2230;}\n</style>\n<script>\n(function(){\n  var p = location.pathname;\n  if (/\\.html$/.test(p)) {\n    var clean = p.replace(/\\.html$/, \"\");\n    if (clean === \"/index\") clean = \"/\";\n    location.replace(clean + location.search + location.hash);\n  }\n})();\n<\\/script>\n</head>\n<body>\n  <div>\n    <h1>That page has moved</h1>\n    <p>If you are not sent on automatically, the fund directory is a good place to start.</p>\n    <p><a href=\"/funds\">Browse every fund</a> &nbsp;&middot;&nbsp; <a href=\"/\">Home</a></p>\n  </div>\n</body>\n</html>"
Path("404.html").write_text(NOT_FOUND)
report["notes"].append("404.html carries old links to the clean address")

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "Stop the redirect loop; carry old links on a 404"], check=False)
subprocess.run(["git", "push"], check=False)