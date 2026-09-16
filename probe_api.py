"""Keep distributions when a fetch comes back empty, and ask the fallback once per fund.

57 funds were showing "yield n/a": the fallback source refuses a full run part
way through, and a fund that came back empty lost the payments it already had,
taking its yield with them. The fallback was also asked twice per empty fund,
doubling the traffic that gets it throttled.
"""
import json, subprocess, ast
from pathlib import Path

PATCH = 'diff --git a/scraper.py b/scraper.py\nindex 54dc5d7..802bde0 100644\n--- a/scraper.py\n+++ b/scraper.py\n@@ -2278,6 +2278,7 @@ def run(registry: list[Fund]) -> list[Fund]:\n     for fund in registry:\n         log.info("Fetching %s (%s) from %s", fund.ticker, fund.issuer, fund.holdings_url)\n         html = None\n+        dh_tried = False  # the fallback is asked once per fund, not twice\n         global ACTIVE_HEADERS\n         ACTIVE_HEADERS = HEADERS_BY_PARSER.get(fund.parser, REQUEST_HEADERS)\n         try:\n@@ -2349,6 +2350,7 @@ def run(registry: list[Fund]) -> list[Fund]:\n                         _d.setdefault("source", "issuer")\n                     if not fund.distributions:\n                         fund.distributions = fetch_dividendhistory(fund)\n+                        dh_tried = True\n                     if fund.distributions:\n                         fund.stats["distribution_source"] = fund.distributions[0].get("source", "issuer")\n                         fund.stats.update(distribution_summary(fund.distributions))\n@@ -2382,11 +2384,23 @@ def run(registry: list[Fund]) -> list[Fund]:\n                 fund.stats["holdings_captured"] = _seed.get("captured", "")\n                 log.info("  -> %d holdings from seed file", len(fund.holdings))\n \n-        if not fund.distributions:\n+        if not fund.distributions and not dh_tried:\n             fund.distributions = fetch_dividendhistory(fund)\n             if fund.distributions:\n                 fund.stats["distribution_source"] = fund.distributions[0].get("source", "issuer")\n                 fund.stats.update(distribution_summary(fund.distributions))\n+\n+        # Never come back with less than we started with. A source refusing us\n+        # today is not evidence that yesterday\'s payments stopped existing, and\n+        # dropping them takes the yield with them (CPCC showed a 6.85% yield\n+        # with no distributions behind it; 57 funds lost their yield outright).\n+        if not fund.distributions:\n+            prev_d = (previous.get(fund.ticker) or {}).get("distributions") or []\n+            if prev_d:\n+                fund.distributions = prev_d\n+                fund.stats["distribution_source"] = prev_d[0].get("source", "issuer")\n+                fund.stats.update(distribution_summary(prev_d))\n+                log.info("  -> kept %d distributions from the previous run", len(prev_d))\n         time.sleep(DELAY_BETWEEN_REQUESTS)\n     return registry\n \n'

report = {}
Path("data").mkdir(exist_ok=True)
Path("/tmp/fix.patch").write_text(PATCH)
r = subprocess.run(["git", "apply", "--check", "/tmp/fix.patch"], capture_output=True, text=True)
if r.returncode == 0:
    subprocess.run(["git", "apply", "/tmp/fix.patch"], check=True)
    report["applied"] = True
else:
    report["applied"] = False
    report["error"] = r.stderr[:300]

t = Path("scraper.py").read_text()
try:
    ast.parse(t); report["parses"] = True
except SyntaxError as exc:
    report["parses"] = False; report["syntax"] = str(exc)[:200]
report["keepsDistributions"] = "distributions from the previous run" in t
report["singleFallback"] = "not dh_tried" in t

Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
if report["applied"] and report["parses"]:
    subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
    subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
    subprocess.run(["git", "add", "scraper.py", "probe_api.py", "data/api-probe.json"], check=False)
    subprocess.run(["git", "commit", "-m", "Keep distributions when a fetch comes back empty, and ask the fallback once per fund"], check=False)
    subprocess.run(["git", "push"], check=False)
