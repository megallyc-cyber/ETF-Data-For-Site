"""A fund page for a fund with no published holdings crashed before it drew.

render() read rows[0] for the "Largest position" card, and for GPIX, GPIQ,
JEPY, CSHI and BALI there is no row 0, so the page showed "Couldn't load the
holdings file" and hid the yield, distributions and next payment it did have.
Fix the template and every page already generated from it.
"""
import json, subprocess
from pathlib import Path

OLD = """        <div class="stat-value">${rows[0][0]}</div>
        <div class="stat-sub">${fmt(rows[0][1],2)}% weight</div>"""
NEW = """        <div class="stat-value">${rows.length ? rows[0][0] : '&mdash;'}</div>
        <div class="stat-sub">${rows.length ? fmt(rows[0][1],2) + '% weight' : 'holdings not published'}</div>"""

changed = []
for page in [Path("fund/index.html")] + sorted(Path("fund").glob("*/index.html")):
    t = page.read_text()
    if OLD in t:
        page.write_text(t.replace(OLD, NEW))
        changed.append(str(page))
report = {"pagesFixed": len(changed), "templateFixed": "fund/index.html" in changed}
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
if report["templateFixed"]:
    subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
    subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
    subprocess.run(["git", "add", "fund", "probe_api.py", "data/api-probe.json"], check=False)
    subprocess.run(["git", "commit", "-m", "A fund with no published holdings should still get its page"], check=False)
    subprocess.run(["git", "push"], check=False)
