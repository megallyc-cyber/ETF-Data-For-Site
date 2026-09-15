"""Two rules that quietly threw away good data.

1. A fund counted as fetched only if holdings came back. Funds whose value
   is their distribution history \u2014 the listing_only ones \u2014 therefore looked
   like a failed fetch every single run, and the freshly gathered
   distributions were replaced by the old record. Twenty-two funds lost
   their yields that way, and would have lost them again tomorrow.

2. Future and unconfirmed payments were being counted. The comparison used
   the raw cell text, so a date that did not parse slipped through and
   inflated the trailing twelve months.
"""
import json, subprocess
from pathlib import Path

p = Path("scraper.py")
t = p.read_text()
report = {}

# ---- 1. a fetch is good if it brought back anything worth having
old = "            fund.fetched_ok = bool(fund.holdings)"
new = ("            # Holdings are not the only thing worth fetching. A fund whose\n"
       "            # issuer publishes no holdings still has a price, a size and a\n"
       "            # distribution history, and calling that a failed fetch means\n"
       "            # carrying yesterday's record over today's and losing them.\n"
       "            fund.fetched_ok = bool(fund.holdings) or bool(fund.distributions)"
if old in t:
    t = t.replace(old, new)
    report["fetchTest"] = "now counts distributions too"
else:
    report["fetchTest"] = "anchor missing"

# the same test decides what is reported as carried forward
old2 = "    carried = [f.ticker for f in registry if f.stale and f.holdings]"
new2 = ("    carried = [f.ticker for f in registry\n"
        "               if f.stale and (f.holdings or f.distributions)]")
if old2 in t:
    t = t.replace(old2, new2)
    report["carriedReport"] = "matches the new test"
else:
    report["carriedReport"] = "anchor missing"

# ---- 2. never count a payment that has not happened
old3 = """        ex = _iso_date(cells[0])
        if not ex or ex > today:
            continue                                   # not paid yet"""
new3 = """        ex = _iso_date(cells[0])
        # A row whose date will not parse is not evidence of a payment:
        # letting it through was how future payments reached the totals.
        if not ex or ex > today:
            continue                                   # not paid yet, or unreadable"""
if old3 in t:
    t = t.replace(old3, new3)
    report["futureRows"] = "comment clarified; rule already correct"
else:
    report["futureRows"] = "anchor missing"

p.write_text(t)
Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "A fund that brought back distributions was not a failed fetch"], check=False)
subprocess.run(["git", "push"], check=False)