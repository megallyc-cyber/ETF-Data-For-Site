"""Actually write the fund pages on each run.

The generator went in but nothing called it, so it produced nothing.
"""
import json, subprocess
from pathlib import Path

p = Path("scraper.py")
t = p.read_text()
report = {}
old = "    write_output(results, merge=filtered)"
new = ("    write_output(results, merge=filtered)\n"
       "    # a page per fund, so a search for a ticker finds us\n"
       "    try:\n"
       "        write_fund_pages(results)\n"
       "    except Exception as exc:  # noqa: BLE001\n"
       "        log.error(\"Could not write fund pages: %s\", exc)")
if old in t and "write_fund_pages(results)" not in t:
    t = t.replace(old, new)
    p.write_text(t)
    report["wired"] = True
else:
    report["wired"] = False
    report["why"] = "anchor missing or already wired"

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "Write the fund pages on every run"], check=False)
subprocess.run(["git", "push"], check=False)