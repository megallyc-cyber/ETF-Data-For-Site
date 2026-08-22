"""
Covered call ETF holdings scraper — Ledger project.

WHERE THIS RUNS
----------------
This script needs outbound access to issuer websites (hamiltonetfs.com,
harvestportfolios.com, bmo.com, globalx.ca, evolveetfs.com, jpmorganfunds.com,
etc). It will NOT run inside a sandboxed dev environment with a restricted
egress allowlist (e.g. one limited to pypi/npm/github). Run it:
  - on your own machine, or
  - as a scheduled GitHub Actions workflow (see .github/workflows/update-data.yml
    example at the bottom of this file), which commits the refreshed JSON back
    to the repo on a cron schedule.

WHAT IT DOES
------------
1. For each fund in FUND_REGISTRY, fetches the issuer's public holdings page
   (most Canadian issuers publish a daily holdings CSV or an HTML table; US
   issuers mostly publish CSV via their fund-data vendor, e.g. SS&C/Confluence).
2. Parses top holdings (ticker, name, weight %).
3. Writes everything to data/funds.json in the schema the website already
   expects (see the FUNDS object in index.html — same shape).

This is a STARTER framework, not a finished, bulletproof scraper: issuer pages
change their markup without notice, some publish only PDFs, and a few only
show sector weights, not per-holding weights. Treat every new issuer as a
small, separate parser function (see the `PARSERS` dict) rather than trying to
write one universal parser — the sites are too different from each other.

Install:
    pip install requests beautifulsoup4 pandas lxml --break-system-packages
"""

import json
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ledger-scraper")

OUTPUT_PATH = Path("data/funds.json")
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LedgerResearchBot/0.1; "
                  "contact: you@example.com) - educational ETF holdings aggregator"
}
REQUEST_TIMEOUT = 20
DELAY_BETWEEN_REQUESTS = 1.5  # be polite, avoid hammering issuer sites


@dataclass
class Fund:
    ticker: str
    name: str
    issuer: str
    region: str          # "CAD" or "US"
    holdings_url: str
    parser: str          # key into PARSERS
    holdings: dict = field(default_factory=dict)  # ticker -> weight_pct
    fetched_ok: bool = False
    error: str = ""


# ---------------------------------------------------------------------------
# 1. FUND REGISTRY
# Add every fund you want tracked here. This is the part you'll grow the most
# over time as you find more issuers and more tickers. Keep it data, not code.
# ---------------------------------------------------------------------------
FUND_REGISTRY: list[Fund] = [
    Fund("HDIV", "Hamilton Enhanced Canadian Covered Call ETF", "Hamilton ETFs", "CAD",
         "https://hamiltonetfs.com/etf/hdiv/", "hamilton"),
    Fund("HYLD", "Hamilton Enhanced U.S. Covered Call ETF", "Hamilton ETFs", "CAD",
         "https://hamiltonetfs.com/etf/hyld/", "hamilton"),
    Fund("HMAX", "Hamilton Canadian Financials Yield Maximizer ETF", "Hamilton ETFs", "CAD",
         "https://hamiltonetfs.com/etf/hmax/", "hamilton"),

    Fund("CMAX", "Hamilton Canadian Equity Yield Maximizer ETF", "Hamilton ETFs", "CAD",
         "https://hamiltonetfs.com/etf/cmax/", "hamilton"),
    Fund("IMAX", "Hamilton International Equity Yield Maximizer ETF", "Hamilton ETFs", "CAD",
         "https://hamiltonetfs.com/etf/imax/", "hamilton"),
    Fund("SMAX", "Hamilton U.S. Equity Yield Maximizer ETF", "Hamilton ETFs", "CAD",
         "https://hamiltonetfs.com/etf/smax/", "hamilton"),
    Fund("UMAX", "Hamilton Utilities Yield Maximizer ETF", "Hamilton ETFs", "CAD",
         "https://hamiltonetfs.com/etf/umax/", "hamilton"),
    Fund("QMAX", "Hamilton Technology Yield Maximizer ETF", "Hamilton ETFs", "CAD",
         "https://hamiltonetfs.com/etf/qmax/", "hamilton"),
    Fund("AMAX", "Hamilton Gold Producer Yield Maximizer ETF", "Hamilton ETFs", "CAD",
         "https://hamiltonetfs.com/etf/amax/", "hamilton"),
    Fund("EMAX", "Hamilton Energy Yield Maximizer ETF", "Hamilton ETFs", "CAD",
         "https://hamiltonetfs.com/etf/emax/", "hamilton"),
    Fund("LMAX", "Hamilton Healthcare Yield Maximizer ETF", "Hamilton ETFs", "CAD",
         "https://hamiltonetfs.com/etf/lmax/", "hamilton"),
    Fund("FMAX", "Hamilton U.S. Financials Yield Maximizer ETF", "Hamilton ETFs", "CAD",
         "https://hamiltonetfs.com/etf/fmax/", "hamilton"),
    Fund("RMAX", "Hamilton REITs Yield Maximizer ETF", "Hamilton ETFs", "CAD",
         "https://hamiltonetfs.com/etf/rmax/", "hamilton"),
    Fund("CDAY", "Hamilton Enhanced Canadian Equity DayMAX ETF", "Hamilton ETFs", "CAD",
         "https://hamiltonetfs.com/etf/cday/", "hamilton"),
    Fund("SDAY", "Hamilton Enhanced U.S. Equity DayMAX ETF", "Hamilton ETFs", "CAD",
         "https://hamiltonetfs.com/etf/sday/", "hamilton"),
    Fund("QDAY", "Hamilton Enhanced Technology DayMAX ETF", "Hamilton ETFs", "CAD",
         "https://hamiltonetfs.com/etf/qday/", "hamilton"),
    Fund("BDAY", "Hamilton Enhanced Bitcoin DayMAX ETF", "Hamilton ETFs", "CAD",
         "https://hamiltonetfs.com/etf/bday/", "hamilton"),

    Fund("ZWB", "BMO Covered Call Canadian Banks ETF", "BMO ETFs", "CAD",
         "https://www.bmoetfs.ca/en/products/zwb", "bmo"),
    Fund("ZWC", "BMO Canadian High Dividend Covered Call ETF", "BMO ETFs", "CAD",
         "https://www.bmoetfs.ca/en/products/zwc", "bmo"),
    Fund("ZWU", "BMO Covered Call Utilities ETF", "BMO ETFs", "CAD",
         "https://www.bmoetfs.ca/en/products/zwu", "bmo"),

    Fund("HHL", "Harvest Healthcare Leaders Income ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etfs/hhl/", "harvest"),
    Fund("HTA", "Harvest Tech Achievers Growth & Income ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/hta/", "harvest"),
    Fund("HBF", "Harvest US Equity Leaders Income ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/hbf/", "harvest"),
    Fund("HUTL", "Harvest Utilities Leaders Income ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/hutl/", "harvest"),
    Fund("HGR", "Harvest REIT Leaders Income ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/hgr/", "harvest"),
    Fund("HPF", "Harvest Energy Leaders Income ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/hpf/", "harvest"),
    Fund("HUBL", "Harvest US Bank Leaders Income ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/hubl/", "harvest"),
    Fund("HLIF", "Harvest Canadian Dividend Leaders Income ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/hlif/", "harvest"),
    Fund("TRVI", "Harvest Travel & Leisure Income ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/trvi/", "harvest"),
    Fund("HIND", "Harvest Industrial Leaders Income ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/hind/", "harvest"),
    Fund("HRIF", "Harvest Diversified Equity Income ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/hrif/", "harvest"),
    Fund("HPYT", "Harvest Premium Yield Treasury ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/hpyt/", "harvest"),
    Fund("HPYM", "Harvest Premium Yield 7-10 Year Treasury ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/hpym/", "harvest"),
    Fund("HBIG", "Harvest Balanced Income Growth ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/hbig/", "harvest"),
    Fund("HHLE", "Harvest Healthcare Leaders Enhanced Income ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/hhle/", "harvest"),
    Fund("HTAE", "Harvest Tech Leaders Enhanced Income ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/htae/", "harvest"),
    Fund("HUTE", "Harvest Utilities Leaders Enhanced Income ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/hute/", "harvest"),
    Fund("HBIE", "Harvest Balanced Income Growth Enhanced ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/hbie/", "harvest"),
    Fund("HDIF", "Harvest Diversified Monthly Income ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/hdif/", "harvest"),
    Fund("HTA", "Harvest Tech Achievers Growth & Income ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/etf/hta/", "harvest"),

    Fund("BANK", "Evolve Canadian Banks and Lifecos Enhanced Yield Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/bank/", "evolve"),
    Fund("CFIN", "Evolve Canadian Financials Yield Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/cfin/", "evolve"),

    Fund("UTES", "Evolve Canadian Utilities Enhanced Yield Index Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/utes/", "evolve"),
    Fund("OILY", "Evolve Canadian Energy Enhanced Yield Index Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/oily/", "evolve"),
    Fund("CUTE", "Evolve Canadian Utilities Yield Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/cute/", "evolve"),
    Fund("ESPX", "Evolve S&P 500 Enhanced Yield Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/espx/", "evolve"),
    Fund("ETSX", "Evolve S&P/TSX 60 Enhanced Yield Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/etsx/", "evolve"),
    Fund("LIFE", "Evolve Global Healthcare Enhanced Yield Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/life/", "evolve"),
    Fund("QQQY", "Evolve NASDAQ Technology Enhanced Yield Index Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/qqqy/", "evolve"),
    Fund("EBNK", "Evolve European Banks Enhanced Yield ETF", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/ebnk/", "evolve"),
    Fund("CALL", "Evolve US Banks Enhanced Yield Fund", "Evolve ETFs", "US",
         "https://evolveetfs.com/product/call/", "evolve"),
    Fund("BASE", "Evolve Global Materials & Mining Enhanced Yield Index ETF", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/base/", "evolve"),
    Fund("LEAD", "Evolve Future Leadership Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/lead/", "evolve"),
    Fund("BOND", "Evolve Enhanced Yield Bond Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/bond/", "evolve"),
    Fund("AGG", "Evolve Canadian Aggregate Bond Enhanced Yield Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/agg/", "evolve"),
    Fund("MIDB", "Evolve Enhanced Yield Mid Term Bond Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/midb/", "evolve"),
    Fund("BIGY", "Evolve US Equity UltraYield ETF", "Evolve ETFs", "US",
         "https://evolveetfs.com/product/bigy/", "evolve"),
    Fund("CANY", "Evolve Canadian Equity UltraYield ETF", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/cany/", "evolve"),
    Fund("SIXY", "Evolve Big Six Canadian Banks UltraYield Index ETF", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/sixy/", "evolve"),
    Fund("INTY", "Evolve International Equity UltraYield ETF", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/inty/", "evolve"),
    Fund("EASY", "Evolve All-in-One UltraYield ETF", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/easy/", "evolve"),
    Fund("TECY", "Evolve NASDAQ Technology UltraYield ETF", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/tecy/", "evolve"),

    Fund("QYLD", "Global X Nasdaq 100 Covered Call ETF", "Global X", "US",
         "https://www.globalxetfs.com/funds/qyld/", "globalx_us"),
    Fund("XYLD", "Global X S&P 500 Covered Call ETF", "Global X", "US",
         "https://www.globalxetfs.com/funds/xyld/", "globalx_us"),
    Fund("RYLD", "Global X Russell 2000 Covered Call ETF", "Global X", "US",
         "https://www.globalxetfs.com/funds/ryld/", "globalx_us"),

    Fund("JEPI", "JPMorgan Equity Premium Income ETF", "J.P. Morgan Asset Management", "US",
         "https://am.jpmorgan.com/us/en/asset-management/adv/products/jpmorgan-equity-premium-income-etf-etf-shares-46641q332", "jpmorgan"),
    Fund("JEPQ", "JPMorgan Nasdaq Equity Premium Income ETF", "J.P. Morgan Asset Management", "US",
         "https://am.jpmorgan.com/us/en/asset-management/adv/products/jpmorgan-nasdaq-equity-premium-income-etf-etf-shares-46654q203", "jpmorgan"),
  

    # Keep adding: Purpose, CI, Brompton, Global X CAD broader lineup,
    # YieldMax (30+ single-stock funds), Simplify, Innovator, NEOS, Amplify...
    Fund("SPXY", "Purpose SpaceX Yield Shares ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/SPXY-yield-shares-purpose-etf", "purpose_single"),
    Fund("TDY", "Purpose TD Yield Shares ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/purpose-td-yield-shares-etf", "purpose_single"),
    Fund("RBCY", "Purpose RBC Yield Shares ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/purpose-rbc-yield-shares-etf", "purpose_single"),
    Fund("BNSY", "Purpose Scotiabank Yield Shares ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/purpose-scotiabank-yield-shares-etf", "purpose_single"),
    Fund("ENBY", "Purpose Enbridge Yield Shares ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/purpose-enbridge-yield-shares-etf", "purpose_single"),
    Fund("SHPY", "Purpose Shopify Yield Shares ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/purpose-shopify-yield-shares-etf", "purpose_single"),
    Fund("CNQY", "Purpose Canadian Natural Resources Yield Shares ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/purpose-canadian-natural-resources-yield-shares-etf", "purpose_single"),
    Fund("TY", "Purpose TELUS Yield Shares ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/purpose-telus-yield-shares-etf", "purpose_single"),
    Fund("DOLY", "Purpose Dollarama Yield Shares ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/purpose-dollarama-yield-shares-etf", "purpose_single"),
    Fund("ATDY", "Purpose Couche-Tard Yield Shares ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/purpose-couche-tard-yield-shares-etf", "purpose_single"),
    Fund("BNY", "Purpose Brookfield Yield Shares ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/purpose-brookfield-yield-shares-etf", "purpose_single"),
    Fund("YMAG", "Tech Innovators Yield Shares Purpose ETF", "Purpose Investments", "US",
         "https://www.purposeinvest.com/funds/tech-innovators-yield-shares-purpose-etf", "purpose_single"),
    Fund("YCST", "Costco Yield Shares Purpose ETF", "Purpose Investments", "US",
         "https://www.purposeinvest.com/funds/costco-yield-shares-purpose-etf", "purpose_single"),
    Fund("YNET", "Netflix Yield Shares Purpose ETF", "Purpose Investments", "US",
         "https://www.purposeinvest.com/funds/netflix-yield-shares-purpose-etf", "purpose_single"),
    Fund("YAVG", "Broadcom Yield Shares Purpose ETF", "Purpose Investments", "US",
         "https://www.purposeinvest.com/funds/broadcom-yield-shares-purpose-etf", "purpose_single"),
    Fund("YCON", "Coinbase Yield Shares Purpose ETF", "Purpose Investments", "US",
         "https://www.purposeinvest.com/funds/coinbase-yield-shares-purpose-etf", "purpose_single"),
    Fund("YPLT", "Palantir Yield Shares Purpose ETF", "Purpose Investments", "US",
         "https://www.purposeinvest.com/funds/palantir-yield-shares-purpose-etf", "purpose_single"),
    Fund("YUNH", "UnitedHealth Yield Shares Purpose ETF", "Purpose Investments", "US",
         "https://www.purposeinvest.com/funds/unitedhealth-yield-shares-purpose-etf", "purpose_single"),
    Fund("YAMD", "AMD Yield Shares Purpose ETF", "Purpose Investments", "US",
         "https://www.purposeinvest.com/funds/amd-yield-shares-purpose-etf", "purpose_single"),
    Fund("YMET", "META Yield Shares Purpose ETF", "Purpose Investments", "US",
         "https://www.purposeinvest.com/funds/meta-yield-shares-purpose-etf", "purpose_single"),
    Fund("YNVD", "NVIDIA Yield Shares Purpose ETF", "Purpose Investments", "US",
         "https://www.purposeinvest.com/funds/nvidia-yield-shares-purpose-etf", "purpose_single"),
    Fund("MSFY", "Microsoft Yield Shares Purpose ETF", "Purpose Investments", "US",
         "https://www.purposeinvest.com/funds/microsoft-yield-shares-purpose-etf", "purpose_single"),
    Fund("YTSL", "Tesla Yield Shares Purpose ETF", "Purpose Investments", "US",
         "https://www.purposeinvest.com/funds/tesla-yield-shares-purpose-etf", "purpose_single"),
    Fund("YAMZ", "Amazon Yield Shares Purpose ETF", "Purpose Investments", "US",
         "https://www.purposeinvest.com/funds/amazon-yield-shares-purpose-etf", "purpose_single"),
    Fund("APLY", "Apple Yield Shares Purpose ETF", "Purpose Investments", "US",
         "https://www.purposeinvest.com/funds/apple-yield-shares-purpose-etf", "purpose_single"),
    Fund("YGOG", "Alphabet Yield Shares Purpose ETF", "Purpose Investments", "US",
         "https://www.purposeinvest.com/funds/alphabet-yield-shares-purpose-etf", "purpose_single"),
    Fund("BRKY", "Berkshire Hathaway Yield Shares Purpose ETF", "Purpose Investments", "US",
         "https://www.purposeinvest.com/funds/berkshire-hathaway-yield-shares-purpose-etf", "purpose_single"),
]


# ---------------------------------------------------------------------------

def parse_purpose_single(html: str) -> dict:
    """Purpose Yield Shares are single-stock covered call funds — holdings are
    essentially 100% the underlying stock plus written call options. The
    underlying ticker appears in the page title in parentheses, e.g.
    'Apple (AAPL) Yield Shares Purpose ETF'."""
    import re
    head_end = html.find("<body")
    head_html = html[:head_end] if head_end != -1 else html
    match = re.search(r"\(([A-Z]{1,5})\)\s+Yield Shares", head_html)
    if not match:
        raise ValueError("could not find underlying ticker in Purpose fund page title")
    return {match.group(1): 100.0}


# 2. PER-ISSUER PARSERS
# Each issuer publishes holdings differently. Write one small function per
# issuer. Return {ticker: weight_pct}. Keep these easy to fix in isolation —
# when an issuer changes their page, only their parser breaks, not everything.
# ---------------------------------------------------------------------------

def parse_hamilton(html: str) -> dict:
    """Hamilton ETFs typically render a holdings table with columns:
    Ticker | Security | Weight (%). Adjust selectors after inspecting the
    live page — this is a starting guess at the structure."""
    soup = BeautifulSoup(html, "lxml")
    holdings = {}
    table = soup.select_one('table[id^="etf-holdings-"]')
    if not table:
        raise ValueError("holdings table not found — page structure may have changed")
    rows = table.select("tr")
    for row in rows[1:]:
        cells = [c.get_text(strip=True) for c in row.select("td")]
        if len(cells) < 3:
            continue
        ticker, weight = cells[0], cells[2]
        if not ticker or not weight:
            continue
        try:
            w = float(weight.replace("%", "").replace(",", ""))
        except ValueError:
            continue
        if w <= 0:
            continue
        holdings[ticker] = w
    return holdings

def parse_bmo(html: str) -> dict:
    """BMO ETF pages usually expose a downloadable holdings CSV link rather
    than an inline table — prefer finding and fetching that CSV directly."""
    soup = BeautifulSoup(html, "lxml")
    holdings = {}
    csv_link = soup.select_one("a[href*='.csv']")
    if csv_link:
        raise ValueError(f"holdings served as CSV at {csv_link.get('href')} — "
                          f"fetch and parse that URL directly instead of the HTML page")
    return holdings


def parse_harvest(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    holdings = {}
    table = soup.select_one('table[id*="_holdings"]')
    if not table:
        raise ValueError("holdings table not found — page structure may have changed")
    rows = table.select("tr")
    for row in rows[1:]:
        cells = [c.get_text(strip=True) for c in row.select("td")]
        if len(cells) < 3:
            continue
        ticker_raw, weight = cells[1], cells[2]
        ticker = ticker_raw.split()[0] if ticker_raw else ""
        if not ticker or not weight:
            continue
        try:
            w = float(weight.replace("%", "").replace(",", ""))
        except ValueError:
            continue
        if w <= 0:
            continue
        holdings[ticker] = w
    return holdings

def parse_evolve(html: str) -> dict:
    import csv
    import re

    match = re.search(r"https://evolveetfs\.com/wp-content/uploads/holdings/[\w\-]+\.csv(?:\?[^\s\"']*)?", html)
    if not match:
        raise ValueError("could not locate the holdings CSV link on the fund page")
    csv_url = match.group(0)

    csv_resp = requests.get(csv_url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    csv_resp.raise_for_status()

    reader = csv.DictReader(csv_resp.text.splitlines())
    holdings = {}
    ticker_re = re.compile(r"^[A-Z]{1,6}([./][A-Z]{1,3})?$")
    for row in reader:
        ticker_raw = (row.get("TICKER") or "").strip()
        name = (row.get("SECURITY_NAME") or "").strip().lower()
        weight_raw = (row.get("PORTFOLIO_MWEIGHT") or "").strip()
        if not ticker_raw or not weight_raw or "option" in name:
            continue
        ticker = ticker_raw.split()[0]
        if not ticker_re.match(ticker):
            continue
        try:
            w = float(weight_raw) * 100
        except ValueError:
            continue
        if w <= 0:
            continue
        holdings[ticker] = round(w, 2)

    if not holdings:
        raise ValueError(f"CSV fetched from {csv_url} but no rows parsed")
    return holdings




def parse_globalx_us(html: str) -> dict:
    """Confirmed CSV schema (Aug 2026): % of Net Assets,Ticker,Name,SEDOL,
    Market Price ($), Shares Held, Market Value ($), with a title line before
    the header row. CSV lives at assets.globalxetfs.com/funds/holdings/
    {ticker}_full-holdings_{YYYYMMDD}.csv, linked from the fund page."""
    import csv
    import re

    soup = BeautifulSoup(html, "lxml")
    csv_link_tag = soup.select_one("a[href*='/funds/holdings/'][href$='.csv']")
    if not csv_link_tag:
        match = re.search(r"https://assets\.globalxetfs\.com/funds/holdings/[\w\-]+\.csv", html)
        if not match:
            raise ValueError("could not locate the holdings CSV link on the fund page")
        csv_url = match.group(0)
    else:
        csv_url = csv_link_tag.get("href")

    csv_resp = requests.get(csv_url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    csv_resp.raise_for_status()

    lines = csv_resp.text.splitlines()
    header_idx = 0
    for i, line in enumerate(lines):
        if line.strip().lower().startswith(("% of net assets", "\ufeff% of net assets")):
            header_idx = i
            break

    reader = csv.DictReader(lines[header_idx:])
    holdings = {}
    ticker_re = re.compile(r"^[A-Z]{1,6}([./][A-Z]{1,3})?$")
    skip_names = ("cash", "payable", "receivable", "future", "index", "swap")
    for row in reader:
        ticker = (row.get("Ticker") or "").strip()
        name = (row.get("Name") or "").strip().lower()
        weight_raw = (row.get("% of Net Assets") or row.get("\ufeff% of Net Assets") or "").strip()
        if not ticker or not weight_raw or not ticker_re.match(ticker):
            continue
        if any(bad in name for bad in skip_names):
            continue
        try:
            w = float(weight_raw.replace("%", "").replace(",", ""))
        except ValueError:
            continue
        if w <= 0:
            continue
        holdings[ticker] = w
      
    if not holdings:
        raise ValueError(f"CSV fetched from {csv_url} but no rows parsed")
    return holdings

def parse_jpmorgan(html: str) -> dict:
    """JPMorgan fund pages are heavily JS-rendered. A static requests.get()
    will likely return an empty shell. This issuer needs a headless browser
    (playwright/selenium) or their public holdings CSV feed if one exists."""
    raise ValueError("JPMorgan fund pages are JS-rendered — use playwright "
                      "or locate their direct CSV/API feed instead of static fetch")


PARSERS: dict[str, Callable[[str], dict]] = {
    "hamilton": parse_hamilton,
    "bmo": parse_bmo,
    "harvest": parse_harvest,
    "evolve": parse_evolve,
    "globalx_us": parse_globalx_us,
    "jpmorgan": parse_jpmorgan,
    "purpose_single": parse_purpose_single,
}


# ---------------------------------------------------------------------------
# 3. FETCH + ORCHESTRATION
# ---------------------------------------------------------------------------

def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def run(registry: list[Fund]) -> list[Fund]:
    for fund in registry:
        log.info("Fetching %s (%s) from %s", fund.ticker, fund.issuer, fund.holdings_url)
        try:
            html = fetch(fund.holdings_url)
            parser = PARSERS[fund.parser]
            fund.holdings = parser(html)
            fund.fetched_ok = bool(fund.holdings)
            if not fund.fetched_ok:
                fund.error = "parser ran but returned no holdings"
        except Exception as exc:  # noqa: BLE001 — log and continue, don't kill the whole run
            fund.fetched_ok = False
            fund.error = str(exc)
            log.warning("  -> FAILED: %s", exc)
        time.sleep(DELAY_BETWEEN_REQUESTS)
    return registry


def write_output(registry: list[Fund], path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {}
    for fund in registry:
        payload[fund.ticker] = {
            "name": fund.name,
            "issuer": fund.issuer,
            "region": fund.region,
            "holdings": fund.holdings,
            "fetched_ok": fund.fetched_ok,
            "error": fund.error,
        }
    path.write_text(json.dumps(payload, indent=2))
    ok = sum(1 for f in registry if f.fetched_ok)
    log.info("Wrote %s — %d/%d funds fetched successfully", path, ok, len(registry))


if __name__ == "__main__":
    results = run(FUND_REGISTRY)
    write_output(results)


# ---------------------------------------------------------------------------
# Example: .github/workflows/update-data.yml
# Save this as a separate file in your repo to automate the weekly/daily run.
# ---------------------------------------------------------------------------
GITHUB_ACTIONS_EXAMPLE = """
name: Update ETF holdings data
on:
  schedule:
    - cron: '0 13 * * 1'   # every Monday 13:00 UTC — adjust to daily if you want
  workflow_dispatch: {}     # lets you trigger it manually from the Actions tab

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install requests beautifulsoup4 lxml
      - run: python scraper.py
      - name: Commit updated data
        run: |
          git config user.name "ledger-bot"
          git config user.email "bot@users.noreply.github.com"
          git add data/funds.json
          git diff --quiet --cached || git commit -m "Update fund holdings data"
          git push
"""
