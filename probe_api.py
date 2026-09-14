"""Why sixteen funds still have no distributions.

Several are marked listing_only, meaning they depend entirely on
dividendhistory.org. Ask that source directly, from the runner, and report
what comes back rather than guessing.
"""
import json, re, urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

def look(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=40) as r:
            html = r.read().decode("utf-8", "replace")
        low = html.lower()
        return {"status": 200, "bytes": len(html),
                "tables": low.count("<table"), "rows": low.count("<tr"),
                "amounts": len(re.findall(r"\\$\\s?\\d+\\.\\d{2,6}", html)),
                "blocked": ("captcha" in low or "just a moment" in low)}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:130]}

report = {}
for t in ["HYGW", "TLTW", "BALI", "JEPI"]:
    report["dividendhistory_" + t] = look("https://dividendhistory.org/payout/" + t + "/")

report["defiance_SPYT"] = look("https://www.defianceetfs.com/spyt-full-holdings/")
report["rex_DACL"] = look("https://www.rexshares.com/dacl/")

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))