"""Twenty-one funds were called "Learn More".

A button label was scraped into the registry as the fund name and has been
sitting in the fund list, the comparison tool and the page titles ever
since. These are the names Global X itself publishes, read from each
product page.
"""
import json, re, subprocess
from pathlib import Path

NAMES = {"AGCC":"Global X Silver Covered Call ETF","BCCC":"Global X Bitcoin Covered Call ETF","BCCL":"Global X Enhanced Bitcoin Covered Call ETF","CPCC":"Global X Copper Producer Equity Covered Call ETF","HGY":"Global X Gold Yield ETF","LPAY":"Global X Long-Term U.S. Treasury Premium Yield ETF","MPAY":"Global X Mid-Term U.S. Treasury Premium Yield ETF","PAYL":"Global X Long-Term Government Bond Premium Yield ETF","PAYM":"Global X Mid-Term Government Bond Premium Yield ETF","PAYS":"Global X Short-Term Government Bond Premium Yield ETF","QQCC":"Global X Nasdaq-100 Covered Call ETF","QQCL":"Global X Enhanced Nasdaq-100 Covered Call ETF","RNCC":"Global X Equal Weight Canadian Telecommunications Covered Call ETF","RNCL":"Global X Enhanced Equal Weight Canadian Telecommunications Covered Call ETF","RSCC":"Global X Russell 2000 Covered Call ETF","RSCL":"Global X Enhanced Russell 2000 Covered Call ETF","SPAY":"Global X Short-Term U.S. Treasury Premium Yield ETF","SVCC":"Global X Silver Miners Covered Call ETF","URCC":"Global X Uranium Covered Call ETF","USCC":"Global X S&P 500 Covered Call ETF","USCL":"Global X Enhanced S&P 500 Covered Call ETF"}

p = Path("scraper.py")
t = p.read_text()
report = {"renamed": [], "missed": []}

for ticker, proper in NAMES.items():
    old = 'Fund("' + ticker + '", "Learn More"'
    new = 'Fund("' + ticker + '", "' + proper + '"'
    if old in t:
        t = t.replace(old, new)
        report["renamed"].append(ticker)
    else:
        report["missed"].append(ticker)

p.write_text(t)
report["remainingLearnMore"] = t.count('"Learn More"')

Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "Give twenty-one funds their real names back"], check=False)
subprocess.run(["git", "push"], check=False)