"""Why do 27 funds still have no distributions?

The dividendhistory fallback is attempted for every fund that has none,
so either the site refuses a runner the way Yahoo now does, or the URL
shape is wrong for these tickers. Ask, rather than guess.
"""
import json, re
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path("data/api-probe.json")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"}


def look(url):
    try:
        with urlopen(Request(url, headers=UA), timeout=45) as r:
            body = r.read().decode("utf-8", "replace")
            code = r.status
    except Exception as exc:
        return {"error": type(exc).__name__ + ": " + str(exc)[:90]}
    # how many rows that look like a payment does the page carry?
    rows = re.findall(r"<tr[^>]*>.*?</tr>", body, re.S)
    money = re.findall(r"\$?\d+\.\d{2,6}", body)
    return {"status": code, "bytes": len(body),
            "tableRows": len(rows), "amountsSeen": len(money),
            "hasDividendTable": "dividend-table" in body,
            "looksBlocked": bool(re.search(r"captcha|cloudflare|access denied|robot", body, re.I))}


report = {}
for t in ("JEPI", "JEPQ", "GPIX", "SPYT", "HYGW"):
    report[t] = {
        "plain": look("https://dividendhistory.org/payout/" + t + "/"),
        "tsx": look("https://dividendhistory.org/payout/tsx/" + t + "/"),
    }
for t in ("CPCC", "SVCC"):
    report[t] = {"tsx": look("https://dividendhistory.org/payout/tsx/" + t + "/")}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))