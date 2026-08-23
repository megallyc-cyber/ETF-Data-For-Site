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
from datetime import datetime, timedelta, timezone
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import re

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ledger-scraper")

OUTPUT_PATH = Path("data/funds.json")
# Some issuers (Hamilton, as of Aug 2026) serve a challenge/interstitial page
# rather than the real one when the request doesn't look like a browser. That
# comes back as a 200 with no holdings table, so it reads as "page structure
# changed" rather than as a block. Sending ordinary browser headers avoids the
# whole category. We still self-identify in the From header and still rate-limit
# ourselves via DELAY_BETWEEN_REQUESTS.
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
    "From": "ledger-etf-holdings-aggregator (educational)",
}
# Evolve is the mirror image of Hamilton: it serves holdings happily to a
# self-identified bot but not to browser headers, so headers can't be a single
# global. ACTIVE_HEADERS is swapped per fund by run() before the parser is
# called, which matters because some parsers (Evolve) fetch a second URL —
# their CSV — from inside the parser and must use the same headers.
LEGACY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LedgerResearchBot/0.1; "
                  "contact: you@example.com) - educational ETF holdings aggregator"
}
HEADERS_BY_PARSER = {
    "evolve": LEGACY_HEADERS,
}
ACTIVE_HEADERS = REQUEST_HEADERS

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
    stats: dict = field(default_factory=dict)     # aum_musd, nav, yield, mer, ...
    distributions: list = field(default_factory=list)  # newest-first payment history
    as_of: str = ""      # UTC date this fund's data was last successfully fetched
    stale: bool = False  # True when we're serving the previous run's data
    fetched_ok: bool = False
    needs_browser: bool = False  # True if the issuer's page requires JS rendering
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
         "https://bmogam.com/ca-en/products/exchange-traded-fund/bmo-covered-call-canadian-banks-etf-zwb/", "bmo", needs_browser=True),
    Fund("ZWC", "BMO Canadian High Dividend Covered Call ETF", "BMO ETFs", "CAD",
         "https://bmogam.com/ca-en/products/exchange-traded-fund/bmo-canadian-high-dividend-covered-call-etf-zwc/", "bmo", needs_browser=True),
    Fund("ZWU", "BMO Covered Call Utilities ETF", "BMO ETFs", "CAD",
         "https://bmogam.com/ca-en/products/exchange-traded-fund/bmo-covered-call-utilities-etf-zwu/", "bmo", needs_browser=True),

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

    # Harvest High Income Shares — a separate product suite on its own URL
    # path (/high-income-shares/), which is why the /etf/ registry missed them.
    # Same page structure, so the existing harvest parser handles them as-is.
    Fund("AEME", "Harvest Agnico Eagle Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/aeme/", "harvest"),
    Fund("AMDY", "Harvest AMD Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/amdy/", "harvest"),
    Fund("AMHE", "Harvest Amazon Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/amhe/", "harvest"),
    Fund("AMZH", "Harvest Amazon High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/amzh/", "harvest"),
    Fund("APLE", "Harvest Apple Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/aple/", "harvest"),
    Fund("AVGY", "Harvest Broadcom Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/avgy/", "harvest"),
    Fund("BCEE", "Harvest BCE Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/bcee/", "harvest"),
    Fund("BLKY", "Harvest Block Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/blky/", "harvest"),
    Fund("CCOE", "Harvest Cameco Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/ccoe/", "harvest"),
    Fund("CNQE", "Harvest CNQ Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/cnqe/", "harvest"),
    Fund("CNYE", "Harvest Coinbase Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/cnye/", "harvest"),
    Fund("CONY", "Harvest Coinbase High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/cony/", "harvest"),
    Fund("COSY", "Harvest Costco Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/cosy/", "harvest"),
    Fund("CRCY", "Harvest Circle Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/crcy/", "harvest"),
    Fund("CRWY", "Harvest CrowdStrike Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/crwy/", "harvest"),
    Fund("ENBE", "Harvest Enbridge Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/enbe/", "harvest"),
    Fund("GOGY", "Harvest Alphabet Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/gogy/", "harvest"),
    Fund("HHIC", "Harvest Canadian High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/hhic/", "harvest"),
    Fund("HHIH", "Harvest High Income Equity Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/hhih/", "harvest"),
    Fund("HHII", "Harvest International High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/hhii/", "harvest"),
    Fund("HHIS", "Harvest Diversified High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/hhis/", "harvest"),
    Fund("HODY", "Harvest Robinhood Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/hody/", "harvest"),
    Fund("JNJY", "Harvest JnJ Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/jnjy/", "harvest"),
    Fund("JPHE", "Harvest JPHE Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/jphe/", "harvest"),
    Fund("LLHE", "Harvest Eli Lilly Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/llhe/", "harvest"),
    Fund("LLYH", "Harvest Eli Lilly High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/llyh/", "harvest"),
    Fund("METE", "Harvest Meta Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/mete/", "harvest"),
    Fund("MSFH", "Harvest Microsoft High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/msfh/", "harvest"),
    Fund("MSHE", "Harvest Microsoft Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/mshe/", "harvest"),
    Fund("MSTE", "Harvest Strategy Inc. Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/mste/", "harvest"),
    Fund("MSTY", "Harvest Strategy Inc. High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/msty/", "harvest"),
    Fund("NFLY", "Harvest Netflix Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/nfly/", "harvest"),
    Fund("NOVY", "Harvest Novo Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/novy/", "harvest"),
    Fund("NVDH", "Harvest NVIDIA High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/nvdh/", "harvest"),
    Fund("NVHE", "Harvest NVIDIA Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/nvhe/", "harvest"),
    Fund("ORCY", "Harvest Oracle Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/orcy/", "harvest"),
    Fund("PLTE", "Harvest Palantir Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/plte/", "harvest"),
    Fund("RDDY", "Harvest Reddit Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/rddy/", "harvest"),
    Fund("RYHE", "Harvest Enhanced High Income RY-Linked Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/ryhe/", "harvest"),
    Fund("SHPE", "Harvest Shopify Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/shpe/", "harvest"),
    Fund("SOFY", "Harvest SoFi Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/sofy/", "harvest"),
    Fund("SPXE", "Harvest SpaceX Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/spxe/", "harvest"),
    Fund("SUHE", "Harvest Suncor Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/suhe/", "harvest"),
    Fund("TDHE", "Harvest Enhanced High Income TD-Linked Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/tdhe/", "harvest"),
    Fund("TEHE", "Harvest TELUS Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/tehe/", "harvest"),
    Fund("TSLY", "Harvest Tesla Enhanced High Income Shares ETF", "Harvest ETFs", "CAD",
         "https://harvestportfolios.com/high-income-shares/tsly/", "harvest"),

    Fund("BANK", "Evolve Canadian Banks and Lifecos Enhanced Yield Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/bank/", "evolve", needs_browser=True),
    Fund("CFIN", "Evolve Canadian Financials Yield Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/cfin/", "evolve", needs_browser=True),

    Fund("UTES", "Evolve Canadian Utilities Enhanced Yield Index Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/utes/", "evolve", needs_browser=True),
    Fund("OILY", "Evolve Canadian Energy Enhanced Yield Index Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/oily/", "evolve", needs_browser=True),
    Fund("CUTE", "Evolve Canadian Utilities Yield Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/cute/", "evolve", needs_browser=True),
    Fund("ESPX", "Evolve S&P 500 Enhanced Yield Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/espx/", "evolve", needs_browser=True),
    Fund("ETSX", "Evolve S&P/TSX 60 Enhanced Yield Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/etsx/", "evolve", needs_browser=True),
    Fund("LIFE", "Evolve Global Healthcare Enhanced Yield Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/life/", "evolve", needs_browser=True),
    Fund("QQQY", "Evolve NASDAQ Technology Enhanced Yield Index Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/qqqy/", "evolve", needs_browser=True),
    Fund("EBNK", "Evolve European Banks Enhanced Yield ETF", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/ebnk/", "evolve", needs_browser=True),
    Fund("CALL", "Evolve US Banks Enhanced Yield Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/call/", "evolve", needs_browser=True),
    Fund("BASE", "Evolve Global Materials & Mining Enhanced Yield Index ETF", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/base/", "evolve", needs_browser=True),
    Fund("LEAD", "Evolve Future Leadership Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/lead/", "evolve", needs_browser=True),
    Fund("BOND", "Evolve Enhanced Yield Bond Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/bond/", "evolve", needs_browser=True),
    Fund("AGG", "Evolve Canadian Aggregate Bond Enhanced Yield Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/agg/", "evolve", needs_browser=True),
    Fund("MIDB", "Evolve Enhanced Yield Mid Term Bond Fund", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/midb/", "evolve", needs_browser=True),
    Fund("BIGY", "Evolve US Equity UltraYield ETF", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/bigy/", "evolve", needs_browser=True),
    Fund("CANY", "Evolve Canadian Equity UltraYield ETF", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/cany/", "evolve", needs_browser=True),
    Fund("SIXY", "Evolve Big Six Canadian Banks UltraYield Index ETF", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/sixy/", "evolve", needs_browser=True),
    Fund("INTY", "Evolve International Equity UltraYield ETF", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/inty/", "evolve", needs_browser=True),
    Fund("EASY", "Evolve All-in-One UltraYield ETF", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/easy/", "evolve", needs_browser=True),
    Fund("TECY", "Evolve NASDAQ Technology UltraYield ETF", "Evolve ETFs", "CAD",
         "https://evolveetfs.com/product/tecy/", "evolve", needs_browser=True),

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
    Fund("YMAG", "Tech Innovators Yield Shares Purpose ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/tech-innovators-yield-shares-purpose-etf", "purpose_multi_unsupported"),
    Fund("YCST", "Costco Yield Shares Purpose ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/costco-yield-shares-purpose-etf", "purpose_single"),
    Fund("YNET", "Netflix Yield Shares Purpose ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/netflix-yield-shares-purpose-etf", "purpose_single"),
    Fund("YAVG", "Broadcom Yield Shares Purpose ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/broadcom-yield-shares-purpose-etf", "purpose_single"),
    Fund("YCON", "Coinbase Yield Shares Purpose ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/coinbase-yield-shares-purpose-etf", "purpose_single"),
    Fund("YPLT", "Palantir Yield Shares Purpose ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/palantir-yield-shares-purpose-etf", "purpose_single"),
    Fund("YUNH", "UnitedHealth Yield Shares Purpose ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/unitedhealth-yield-shares-purpose-etf", "purpose_single"),
    Fund("YAMD", "AMD Yield Shares Purpose ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/amd-yield-shares-purpose-etf", "purpose_single"),
    Fund("YMET", "META Yield Shares Purpose ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/meta-yield-shares-purpose-etf", "purpose_single"),
    Fund("YNVD", "NVIDIA Yield Shares Purpose ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/nvidia-yield-shares-purpose-etf", "purpose_single"),
    Fund("MSFY", "Microsoft Yield Shares Purpose ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/microsoft-yield-shares-purpose-etf", "purpose_single"),
    Fund("YTSL", "Tesla Yield Shares Purpose ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/tesla-yield-shares-purpose-etf", "purpose_single"),
    Fund("YAMZ", "Amazon Yield Shares Purpose ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/amazon-yield-shares-purpose-etf", "purpose_single"),
    Fund("APLY", "Apple Yield Shares Purpose ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/apple-yield-shares-purpose-etf", "purpose_single"),
    Fund("YGOG", "Alphabet Yield Shares Purpose ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/alphabet-yield-shares-purpose-etf", "purpose_single"),
    Fund("BRKY", "Berkshire Hathaway Yield Shares Purpose ETF", "Purpose Investments", "CAD",
         "https://www.purposeinvest.com/funds/berkshire-hathaway-yield-shares-purpose-etf", "purpose_single"),
    Fund("JEPI", "JPMorgan Equity Premium Income ETF", "J.P. Morgan Asset Management", "US",
         "https://am.jpmorgan.com/FundsMarketingHandler/excel?type=dailyETFHoldings&cusip=46641Q332&country=us&role=adv&fundType=N_ETF&locale=en-US&isUnderlyingHolding=false&isProxyHolding=false", "jpmorgan_xls"),
    Fund("JEPQ", "JPMorgan Nasdaq Equity Premium Income ETF", "J.P. Morgan Asset Management", "US",
         "https://am.jpmorgan.com/FundsMarketingHandler/excel?type=dailyETFHoldings&cusip=46654Q203&country=us&role=adv&fundType=N_ETF&locale=en-US&isUnderlyingHolding=false&isProxyHolding=false", "jpmorgan_xls"),
    Fund("SPYI", "NEOS S&P 500 High Income ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-admin/admin-ajax.php?action=download_holdings_csv&ticker=SPYI", "neos_csv"),
    Fund("QQQI", "NEOS Nasdaq-100 High Income ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-admin/admin-ajax.php?action=download_holdings_csv&ticker=QQQI", "neos_csv"),
    Fund("IWMI", "NEOS Russell 2000 High Income ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-admin/admin-ajax.php?action=download_holdings_csv&ticker=IWMI", "neos_csv"),
    Fund("BTCI", "NEOS Bitcoin High Income ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-admin/admin-ajax.php?action=download_holdings_csv&ticker=BTCI", "neos_csv"),
    Fund("QQQH", "NEOS Nasdaq-100 Hedged Equity Income ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-admin/admin-ajax.php?action=download_holdings_csv&ticker=QQQH", "neos_csv"),
    Fund("SPYH", "NEOS S&P 500 Hedged Equity Income ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-admin/admin-ajax.php?action=download_holdings_csv&ticker=SPYH", "neos_csv"),
    Fund("MLPI", "NEOS MLP & Energy Infrastructure High Income ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-admin/admin-ajax.php?action=download_holdings_csv&ticker=MLPI", "neos_csv"),
    Fund("IYRI", "NEOS Real Estate High Income ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-admin/admin-ajax.php?action=download_holdings_csv&ticker=IYRI", "neos_csv"),
    Fund("IAUI", "NEOS Gold High Income ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-admin/admin-ajax.php?action=download_holdings_csv&ticker=IAUI", "neos_csv"),
    Fund("DIVO", "Amplify CWP Enhanced Dividend Income ETF", "Amplify ETFs", "US",
         "https://amplifyetfs.com/divo-holdings/", "amplify_rendered", needs_browser=True),
    Fund("IDVO", "Amplify CWP International Enhanced Dividend Income ETF", "Amplify ETFs", "US",
         "https://amplifyetfs.com/idvo-holdings/", "amplify_rendered", needs_browser=True),
    Fund("QDVO", "Amplify CWP Growth & Income ETF", "Amplify ETFs", "US",
         "https://amplifyetfs.com/qdvo-holdings/", "amplify_rendered", needs_browser=True),
    Fund("CNCC", "Global X S&P/TSX 60 Covered Call ETF", "Global X Canada", "CAD",
                  "https://www.globalx.ca/product/cncc#holdings", "globalx_ca_rendered", needs_browser=True),
    Fund("CNCL", "Global X Enhanced S&P/TSX 60 Covered Call ETF", "Global X Canada", "CAD",
                  "https://www.globalx.ca/product/cncl#holdings", "globalx_ca_rendered", needs_browser=True),
    Fund("BKCC", "Global X Equal Weight Canadian Bank Covered Call ETF", "Global X Canada", "CAD",
                  "https://www.globalx.ca/product/bkcc#holdings", "globalx_ca_rendered", needs_browser=True),
    Fund("BKCL", "Global X Enhanced Equal Weight Canadian Banks Covered Call ETF", "Global X Canada", "CAD",
                  "https://www.globalx.ca/product/bkcl#holdings", "globalx_ca_rendered", needs_browser=True),
    Fund("EACC", "Global X MSCI EAFE Covered Call ETF", "Global X Canada", "CAD",
                  "https://www.globalx.ca/product/eacc#holdings", "globalx_ca_rendered", needs_browser=True),
    Fund("EACL", "Global X Enhanced MSCI EAFE Covered Call ETF", "Global X Canada", "CAD",
                  "https://www.globalx.ca/product/eacl#holdings", "globalx_ca_rendered", needs_browser=True),
    Fund("EMCC", "Global X MSCI Emerging Markets Covered Call ETF", "Global X Canada", "CAD",
                  "https://www.globalx.ca/product/emcc#holdings", "globalx_ca_rendered", needs_browser=True),
    Fund("EMCL", "Global X Enhanced MSCI Emerging Markets Covered Call ETF", "Global X Canada", "CAD",
                  "https://www.globalx.ca/product/emcl#holdings", "globalx_ca_rendered", needs_browser=True),
    Fund("ENCC", "Global X Canadian Oil and Gas Equity Covered Call ETF", "Global X Canada", "CAD",
                  "https://www.globalx.ca/product/encc#holdings", "globalx_ca_rendered", needs_browser=True),
    Fund("ENCL", "Global X Enhanced Canadian Oil and Gas Equity Covered Call ETF", "Global X Canada", "CAD",
                  "https://www.globalx.ca/product/encl#holdings", "globalx_ca_rendered", needs_browser=True),
    Fund("EQCC", "Global X All-Equity Asset Allocation Covered Call ETF", "Global X Canada", "CAD",
                  "https://www.globalx.ca/product/eqcc#holdings", "globalx_ca_rendered", needs_browser=True),
    Fund("EQCL", "Global X Enhanced All-Equity Asset Allocation Covered Call ETF", "Global X Canada", "CAD",
                  "https://www.globalx.ca/product/eqcl#holdings", "globalx_ca_rendered", needs_browser=True),
    Fund("GLCC", "Global X Gold Producer Equity Covered Call ETF", "Global X Canada", "CAD",
                  "https://www.globalx.ca/product/glcc#holdings", "globalx_ca_rendered", needs_browser=True),
    Fund("GLCL", "Global X Enhanced Gold Producer Equity Covered Call ETF", "Global X Canada", "CAD",
                  "https://www.globalx.ca/product/glcl#holdings", "globalx_ca_rendered", needs_browser=True),
    Fund("GRCC", "Global X Growth Asset Allocation Covered Call ETF", "Global X Canada", "CAD",
                  "https://www.globalx.ca/product/grcc#holdings", "globalx_ca_rendered", needs_browser=True),
  
    # NEOS funds the registry was missing
    Fund("BNDI", "NEOS Enhanced Income Aggregate Bond ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-content/fundwebsite/holdings/BNDI_holdings.csv", "neos_csv"),
    Fund("CSHI", "NEOS Enhanced Income Cash Alternative ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-content/fundwebsite/holdings/CSHI_holdings.csv", "neos_csv"),
    Fund("HYBI", "NEOS Enhanced Income Credit Select ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-content/fundwebsite/holdings/HYBI_holdings.csv", "neos_csv"),
    Fund("NEHI", "NEOS Nasdaq-100 Hedged Equity Income ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-content/fundwebsite/holdings/NEHI_holdings.csv", "neos_csv"),
    Fund("NIHI", "NEOS S&P 500 Hedged Equity Income ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-content/fundwebsite/holdings/NIHI_holdings.csv", "neos_csv"),
    Fund("NLSI", "NEOS Large Cap Systematic Income ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-content/fundwebsite/holdings/NLSI_holdings.csv", "neos_csv"),
    Fund("TLTI", "NEOS Enhanced Income 20+ Year Treasury ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-content/fundwebsite/holdings/TLTI_holdings.csv", "neos_csv"),
    Fund("XBCI", "NEOS Bitcoin High Income ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-content/fundwebsite/holdings/XBCI_holdings.csv", "neos_csv"),
    Fund("XQQI", "NEOS Nasdaq-100 High Income ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-content/fundwebsite/holdings/XQQI_holdings.csv", "neos_csv"),
    Fund("XSPI", "NEOS S&P 500 High Income ETF", "NEOS Investments", "US",
         "https://neosfunds.com/wp-content/fundwebsite/holdings/XSPI_holdings.csv", "neos_csv"),

    # Broader US option-income universe. Holdings are not parsed for these
    # (each issuer would need its own parser); they carry price history,
    # distributions and a computed yield, and say so on the fund page.
    Fund("GPIX", "Goldman Sachs S&P 500 Core Premium Income ETF", "Goldman Sachs", "US",
         "https://dividendhistory.org/payout/GPIX/", "listing_only"),
    Fund("GPIQ", "Goldman Sachs Nasdaq-100 Core Premium Income ETF", "Goldman Sachs", "US",
         "https://dividendhistory.org/payout/GPIQ/", "listing_only"),
    Fund("XDTE", "Roundhill S&P 500 0DTE Covered Call Strategy ETF", "Roundhill", "US",
         "https://dividendhistory.org/payout/XDTE/", "listing_only"),
    Fund("QDTE", "Roundhill Innovation-100 0DTE Covered Call Strategy ETF", "Roundhill", "US",
         "https://dividendhistory.org/payout/QDTE/", "listing_only"),
    Fund("RDTE", "Roundhill Small Cap 0DTE Covered Call Strategy ETF", "Roundhill", "US",
         "https://dividendhistory.org/payout/RDTE/", "listing_only"),
    Fund("QQQT", "Defiance Nasdaq-100 Enhanced Options Income ETF", "Defiance", "US",
         "https://dividendhistory.org/payout/QQQT/", "listing_only"),
    Fund("SPYT", "Defiance S&P 500 Enhanced Options Income ETF", "Defiance", "US",
         "https://dividendhistory.org/payout/SPYT/", "listing_only"),
    Fund("IWMT", "Defiance R2000 Enhanced Options Income ETF", "Defiance", "US",
         "https://dividendhistory.org/payout/IWMT/", "listing_only"),
    Fund("FEPI", "REX FANG & Innovation Equity Premium Income ETF", "REX Shares", "US",
         "https://dividendhistory.org/payout/FEPI/", "listing_only"),
    Fund("AIPI", "REX AI Equity Premium Income ETF", "REX Shares", "US",
         "https://dividendhistory.org/payout/AIPI/", "listing_only"),
    Fund("BALI", "iShares Advantage Large Cap Income ETF", "iShares", "US",
         "https://dividendhistory.org/payout/BALI/", "listing_only"),
    Fund("TLTW", "iShares 20+ Year Treasury Bond BuyWrite Strategy ETF", "iShares", "US",
         "https://dividendhistory.org/payout/TLTW/", "listing_only"),
    Fund("HYGW", "iShares High Yield Corporate Bond BuyWrite Strategy ETF", "iShares", "US",
         "https://dividendhistory.org/payout/HYGW/", "listing_only"),
    Fund("LQDW", "iShares Investment Grade Corporate Bond BuyWrite Strategy ETF", "iShares", "US",
         "https://dividendhistory.org/payout/LQDW/", "listing_only"),
    Fund("QYLG", "Global X Nasdaq 100 Covered Call & Growth ETF", "Global X", "US",
         "https://dividendhistory.org/payout/QYLG/", "listing_only"),
    Fund("XYLG", "Global X S&P 500 Covered Call & Growth ETF", "Global X", "US",
         "https://dividendhistory.org/payout/XYLG/", "listing_only"),
    Fund("RYLG", "Global X Russell 2000 Covered Call & Growth ETF", "Global X", "US",
         "https://dividendhistory.org/payout/RYLG/", "listing_only"),
    Fund("DJIA", "Global X Dow 30 Covered Call ETF", "Global X", "US",
         "https://dividendhistory.org/payout/DJIA/", "listing_only"),
    Fund("QRMI", "Global X Nasdaq 100 Risk Managed Income ETF", "Global X", "US",
         "https://dividendhistory.org/payout/QRMI/", "listing_only"),
    Fund("XRMI", "Global X S&P 500 Risk Managed Income ETF", "Global X", "US",
         "https://dividendhistory.org/payout/XRMI/", "listing_only"),
    Fund("EAPR", "Global X S&P 500 Tail Risk ETF", "Global X", "US",
         "https://dividendhistory.org/payout/EAPR/", "listing_only"),
    Fund("ISPY", "ProShares S&P 500 High Income ETF", "ProShares", "US",
         "https://dividendhistory.org/payout/ISPY/", "listing_only"),
    Fund("IQQQ", "ProShares Nasdaq-100 High Income ETF", "ProShares", "US",
         "https://dividendhistory.org/payout/IQQQ/", "listing_only"),
    Fund("JEPY", "Defiance S&P 500 Enhanced Options Income ETF", "Defiance", "US",
         "https://dividendhistory.org/payout/JEPY/", "listing_only"),
    Fund("ULTY", "YieldMax Ultra Option Income Strategy ETF", "YieldMax", "US",
         "https://dividendhistory.org/payout/ULTY/", "listing_only"),
    Fund("YMAX", "YieldMax Universe Fund of Option Income ETFs", "YieldMax", "US",
         "https://dividendhistory.org/payout/YMAX/", "listing_only"),
    Fund("NVDY", "YieldMax NVDA Option Income Strategy ETF", "YieldMax", "US",
         "https://dividendhistory.org/payout/NVDY/", "listing_only"),
    Fund("AMZY", "YieldMax AMZN Option Income Strategy ETF", "YieldMax", "US",
         "https://dividendhistory.org/payout/AMZY/", "listing_only"),
    Fund("GOOY", "YieldMax GOOGL Option Income Strategy ETF", "YieldMax", "US",
         "https://dividendhistory.org/payout/GOOY/", "listing_only"),
    Fund("FBY", "YieldMax META Option Income Strategy ETF", "YieldMax", "US",
         "https://dividendhistory.org/payout/FBY/", "listing_only"),
    Fund("MSFO", "YieldMax MSFT Option Income Strategy ETF", "YieldMax", "US",
         "https://dividendhistory.org/payout/MSFO/", "listing_only"),
    Fund("PLTY", "YieldMax PLTR Option Income Strategy ETF", "YieldMax", "US",
         "https://dividendhistory.org/payout/PLTY/", "listing_only"),
    Fund("SMCY", "YieldMax SMCI Option Income Strategy ETF", "YieldMax", "US",
         "https://dividendhistory.org/payout/SMCY/", "listing_only"),
    Fund("GDXY", "YieldMax Gold Miners Option Income Strategy ETF", "YieldMax", "US",
         "https://dividendhistory.org/payout/GDXY/", "listing_only"),

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

def parse_listing_only(html: str) -> dict:
    """No holdings — deliberately.

    Some issuers render holdings behind JavaScript or a login, and inventing a
    parser per issuer is a bigger job than it's worth for breadth. Listing a
    fund with an empty holdings dict still gives it a price series, a full
    distribution history from the fallback and therefore a computed yield, so
    it is useful on the site and honest about what's missing. Holdings show as
    unavailable rather than wrong.
    """
    return {}


def parse_bmo(html: str) -> dict:
    """BMO moved to bmogam.com and renders holdings after page load, so this
    needs the browser fetch. The table is headed
    Weight | Name | ISIN | Bloomberg Ticker | ... and the Bloomberg column is
    the clean ticker we want; the name column would need fuzzy matching.
    """
    soup = BeautifulSoup(html, "lxml")
    holdings = {}
    for table in soup.find_all("table"):
        head = table.find("tr")
        if not head:
            continue
        cols = [c.get_text(" ", strip=True).lower() for c in head.find_all(["th", "td"])]
        if "weight" not in cols or not any("bloomberg" in c for c in cols):
            continue
        i_w = cols.index("weight")
        i_t = next(i for i, c in enumerate(cols) if "bloomberg" in c)
        for tr in table.find_all("tr")[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
            if len(cells) <= max(i_w, i_t):
                continue
            ticker = cells[i_t].strip().upper()
            m = re.search(r"(-?[\d.]+)\s*%", cells[i_w])
            if not ticker or ticker in {"—", "-"} or not m:
                continue
            weight = float(m.group(1))
            if weight <= 0:
                continue          # cash and derivative lines can be zero or negative
            holdings[ticker] = holdings.get(ticker, 0.0) + weight
        if holdings:
            break
    return holdings


def _harvest_name_index() -> dict:
    """Map normalised Harvest fund names -> our registry tickers, so that a
    Harvest fund-of-funds row that only gives a fund NAME (its Ticker cell is
    empty) resolves to a real ticker instead of collapsing to 'Harvest'."""
    # Harvest markets some funds under a name that differs from the legal
    # name we hold in the registry, so a pure name match misses them.
    index = {
        "harvest tech leaders income etf": "HTA",
        "harvest canadian equity income leaders etf": "HLIF",
    }
    for f in FUND_REGISTRY:
        if f.issuer == "Harvest ETFs":
            index[_norm_fund_name(f.name)] = f.ticker
    return index


def _norm_fund_name(name: str) -> str:
    import re
    n = name.lower()
    n = re.sub(r"[0-9]+$", "", n.strip())          # strip trailing footnote markers
    n = n.replace("&", "and")
    n = re.sub(r"[^a-z ]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def parse_harvest(html: str) -> dict:
    """Harvest publishes two different column orders on the same table id:
    equity funds are  Name | Ticker | Weight | Sector | Country
    fund-of-funds are Ticker | ETF Name | Weight | Sector | Country
    and on the fund-of-funds pages the Ticker cell is empty. Reading a fixed
    column index therefore silently produced 'Harvest' for every row (all
    colliding on one dict key). Read the header row instead, and fall back to
    the fund name -> registry ticker when the ticker cell is blank."""
    soup = BeautifulSoup(html, "lxml")
    holdings = {}
    table = soup.select_one('table[id*="_holdings"]')
    if not table:
        raise ValueError("holdings table not found — page structure may have changed")

    rows = table.select("tr")
    if not rows:
        raise ValueError("holdings table has no rows")

    header = [c.get_text(strip=True).lower() for c in rows[0].select("th,td")]
    def col(*names, default=None):
        for i, h in enumerate(header):
            for n in names:
                if n in h:
                    return i
        return default

    i_ticker = col("ticker", default=0)
    i_name = col("name", default=1)
    i_weight = col("weight", "%", default=2)
    name_index = _harvest_name_index()

    for row in rows[1:]:
        cells = [c.get_text(strip=True) for c in row.select("td")]
        if len(cells) <= max(i_ticker, i_weight):
            continue

        raw_ticker = cells[i_ticker] if i_ticker < len(cells) else ""
        raw_name = cells[i_name] if i_name is not None and i_name < len(cells) else ""
        weight = cells[i_weight]

        # "REGN US" -> "REGN"; blank ticker -> resolve the fund name
        ticker = raw_ticker.split()[0] if raw_ticker else ""
        if not ticker and raw_name:
            ticker = name_index.get(_norm_fund_name(raw_name), raw_name.strip())
        if not ticker or not weight:
            continue

        try:
            w = float(weight.replace("%", "").replace(",", ""))
        except ValueError:
            continue
        if w <= 0:
            continue
        # same underlying can appear twice (e.g. two share classes) — add, don't clobber
        holdings[ticker] = round(holdings.get(ticker, 0.0) + w, 4)

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

def parse_jpmorgan_xls(html: str) -> dict:
    """JPMorgan publishes a 'Download all holdings (XLS)' export as a real .xlsx
    file behind a static, parameterized URL — no JS rendering needed. This
    function is called with the RAW BYTES of that xlsx (see fetch_binary in
    run()), passed through as a latin-1 decoded string so it can flow through
    the same str-based parser interface as every other issuer."""
    import io
    import re
    from openpyxl import load_workbook
    raw_bytes = html.encode("latin-1")
    wb = load_workbook(io.BytesIO(raw_bytes), data_only=True, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header_idx = None
    sym_col = pct_col = None
    for i, row in enumerate(rows):
        cells = [str(c).strip().lower() if c is not None else "" for c in row]
        if "ticker" in cells and any("net assets" in c for c in cells):
            header_idx = i
            sym_col = cells.index("ticker")
            pct_col = next(j for j, c in enumerate(cells) if "net assets" in c)
            break
    if header_idx is None:
        raise ValueError("could not find a 'Symbol' + '% of Net Assets' header row in the xlsx")
    holdings = {}
    ticker_re = re.compile(r"^[A-Z]{1,6}([./][A-Z]{1,3})?$")
    for row in rows[header_idx + 1:]:
        if row is None or len(row) <= max(sym_col, pct_col):
            continue
        ticker = str(row[sym_col]).strip() if row[sym_col] is not None else ""
        pct_raw = row[pct_col]
        if not ticker or not ticker_re.match(ticker) or pct_raw is None:
            continue
        try:
            pct_str = str(pct_raw).replace("%", "").strip()
            w_val = float(pct_str)
            w = w_val
        except (TypeError, ValueError):
            continue
        if w <= 0:
            continue
        holdings[ticker] = round(w, 2)
    if not holdings:
        raise ValueError("xlsx parsed but no holdings rows matched")
    return holdings

def parse_neos_csv(html: str) -> dict:
    """NEOS publishes a plain-text CSV export at a static admin-ajax URL
    (columns: Date, Account, StockTicker, Cusip, SecurityName, Shares, Price,
    MarketValue, Weightings, ...). No JS rendering needed."""
    import csv
    import re
    reader = csv.DictReader(html.splitlines())
    holdings = {}
    ticker_re = re.compile(r"^[A-Z]{1,6}([./][A-Z]{1,3})?$")
    for row in reader:
        ticker = (row.get("StockTicker") or "").strip()
        weight_raw = (row.get("Weightings") or "").strip()
        if not ticker or not weight_raw or not ticker_re.match(ticker):
            continue
        try:
            w = float(weight_raw.replace("%", "").replace(",", ""))
        except ValueError:
            continue
        if w <= 0:
            continue
        holdings[ticker] = round(w, 2)
    if not holdings:
        raise ValueError("NEOS csv fetched but no holdings rows parsed")
    return holdings

def parse_amplify_rendered(html: str) -> dict:
    """Amplify's holdings pages populate a table client-side from Firestore —
    this parser receives already-RENDERED html (see fetch_rendered in run())
    with the table already populated. Table columns: Name | Ticker |
    Market Value (%) | CUSIP | Shares | Market Value ($)."""
    import re
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table")
    if not table:
        raise ValueError("holdings table not found in rendered page")
    rows = table.select("tr")
    holdings = {}
    ticker_re = re.compile(r"^[A-Z]{1,6}([./][A-Z]{1,3})?$")
    for row in rows[1:]:
        cells = [c.get_text(strip=True) for c in row.select("td")]
        if len(cells) < 3:
            continue
        ticker, weight = cells[1], cells[2]
        if not ticker or not weight or not ticker_re.match(ticker):
            continue
        try:
            w = float(weight.replace("%", "").replace(",", ""))
        except ValueError:
            continue
        if w <= 0:
            continue
        holdings[ticker] = round(w, 2)
    if not holdings:
        raise ValueError("rendered page fetched but no holdings rows parsed")
    return holdings

def parse_globalx_ca_rendered(html: str) -> dict:
    """Global X Canada's Holdings tab is client-rendered and, worse, its
    'Top Underlying Holdings' section lists company NAMES, not tickers —
    unusable for ticker-based overlap without a name->ticker map. Instead we
    read the 'Top Holdings' section just above it, which lists the actual
    wrapped fund/ticker this ETF holds, e.g. 'GLOBAL X S&P/TSX 60 INDEX ETF
    (CNDX)  100.00%'. This gives one real ticker per fund rather than
    dozens of unmatched names — a genuine, if partial, overlap signal."""
    import re
    match = re.search(r"\(([A-Z]{1,6})\)[\s\S]{1,500}?(\d+\.\d+)%", html)
    if not match:
        raise ValueError("could not find a wrapped-ticker top holding in rendered page")
    ticker, weight = match.group(1), match.group(2)
    w = float(weight)
    if w <= 0:
        raise ValueError("parsed a zero-weight top holding")
    return {ticker: round(w, 2)}
  




# ---------------------------------------------------------------------------
# 2b. FUND STATS (AUM / NAV / yield / MER)
#
# None of this lives in the holdings files — it sits in the "key facts" block
# on each issuer's fund page. Every issuer renders that block differently in
# HTML, but they all render it as label-then-value in READING ORDER, so rather
# than nine bespoke selectors we flatten the page to text lines once and look
# for a label, then scan the next few lines for the first value that matches
# the shape we expect (money / percent). That survives markup changes.
#
# Issuers with no AUM on the fetched page (Hamilton, J.P. Morgan) simply
# return {} — the site treats missing stats as "not collected", not as zero.
# ---------------------------------------------------------------------------

MONEY_RE = re.compile(
    r"\$\s?([\d,]+(?:\.\d+)?)\s*(billion|million|thousand|bn|mm|[BMK])?\b",
    re.IGNORECASE,
)
PERCENT_RE = re.compile(r"(-?[\d.]+)\s*%")

MULTIPLIER = {
    "b": 1000.0, "bn": 1000.0, "billion": 1000.0,
    "m": 1.0, "mm": 1.0, "million": 1.0,
    "k": 0.001, "thousand": 0.001,
}


def _text_lines(html: str) -> list:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    raw = soup.get_text("\n")
    return [ln.strip() for ln in raw.split("\n") if ln.strip()]


def _money_to_millions(text: str):
    """'$8.36 billion' / '$1.275 B' / '$2133.67M' / '$194,678,118' -> millions."""
    m = MONEY_RE.search(text)
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    if unit:
        return round(value * MULTIPLIER.get(unit, 1.0), 3)
    # a bare figure is in dollars, not millions
    return round(value / 1_000_000, 3)


def _find_after(lines: list, labels: list, pattern, lookahead: int = 6):
    """Find a label line, then return the first match for `pattern` in the rest
    of that line or in the next few lines. Tooltips and blank cells often sit
    between a label and its value, which is why we look ahead rather than
    trusting the very next line."""
    for i, line in enumerate(lines):
        low = line.lower().strip().lstrip("\u2022 ").rstrip("*: ").strip()
        matched = None
        for w in labels:
            if low == w or re.match(re.escape(w) + r"\b", low):
                matched = w
                break
        if not matched:
            continue
        rest = line.lower().split(matched, 1)[-1]
        m = pattern.search(line[len(line) - len(rest):]) if rest else None
        if m:
            return matched, m.group(0).strip()
        for candidate in lines[i + 1 : i + 1 + lookahead]:
            m = pattern.search(candidate)
            if m:
                return matched, m.group(0).strip()
    return None


AUM_LABELS = ["net aum", "aum", "net assets", "fund total net assets",
              "total net assets", "fund size", "assets under management",
              # Hamilton's fund-facts table just says "Assets" ($2489.4M CAD)
              "assets"]
NAV_LABELS = ["nav", "net asset value", "closing nav"]
YIELD_LABELS = ["current annualized yield", "current yield", "distribution yield",
                "trailing 12-month yield", "yield %", "annualized distribution yield",
                "30-day sec yield", "annualized yield"]
MER_LABELS = ["management expense ratio", "mer", "total expense ratio",
              "total annual fund operating expenses", "expense ratio"]
FEE_LABELS = ["management fee", "mgmt fee"]


def parse_fund_stats(html: str) -> dict:
    """Issuer-agnostic key-facts reader. Returns only the keys it actually
    found, so a partially-populated page degrades to partial stats.

    Yield and MER are stored with the label the issuer used, because those
    labels are not interchangeable across issuers: Global X US publishes a
    30-day SEC yield (0.02% for QYLD) while Global X Canada publishes an
    annualised distribution yield (6.65% for CNCC). Showing either as a bare
    "Yield" would be actively misleading, so the site prints the issuer's own
    wording.
    """
    lines = _text_lines(html)
    stats = {}

    hit = _find_after(lines, AUM_LABELS, MONEY_RE)
    if hit:
        millions = _money_to_millions(hit[1])
        # sanity floor/ceiling: $0.0M or $50T means we matched the wrong line
        if millions is not None and 0.05 <= millions <= 5_000_000:
            stats["aum_musd"] = millions
            stats["aum_display"] = hit[1]

    hit = _find_after(lines, NAV_LABELS, MONEY_RE)
    if hit:
        stats["nav"] = hit[1]

    hit = _find_after(lines, YIELD_LABELS, PERCENT_RE)
    if hit:
        stats["yield"] = hit[1]
        stats["yield_label"] = hit[0]

    hit = _find_after(lines, MER_LABELS, PERCENT_RE)
    if hit:
        stats["mer"] = hit[1]
        stats["mer_label"] = hit[0]

    # Purpose builds its pages without <table> elements, so there is no history
    # to parse — but the key-facts block does carry the most recent payment, and
    # one real number beats an empty distributions section.
    hit = _find_after(lines, ["last distribution", "latest distribution"], MONEY_RE)
    if hit:
        stats["last_amount"] = float(hit[1].replace("$", "").replace(",", "").strip())
        for ln in lines:
            m = re.search(r"\((20\d{2}-\d{2}-\d{2})\)", ln)
            if m:
                stats["last_ex_date"] = m.group(1)
                break

    hit = _find_after(lines, FEE_LABELS, PERCENT_RE)
    if hit:
        stats["mgmt_fee"] = hit[1]

    return stats


# Which issuers expose key facts on a page we can reach, and where.
# Value is either None (reuse the holdings page we already fetched) or a
# callable turning a Fund into the profile URL to fetch separately.
STATS_SOURCES = {
    "harvest": None,
    "purpose_single": None,
    "evolve": None,
    "globalx_us": None,
    "globalx_ca_rendered": None,
    "neos_csv": lambda f: f"https://neosfunds.com/{f.ticker.lower()}/",
    "amplify_rendered": lambda f: f"https://amplifyetfs.com/{f.ticker.lower()}/",
    # hamilton: fund page carries NAV + yield but no AUM
    "hamilton": None,
    # jpmorgan: holdings come from an .xlsx export, key facts are behind JS
}


PARSERS: dict[str, Callable[[str], dict]] = {
    "listing_only": parse_listing_only,
    "hamilton": parse_hamilton,
    "bmo": parse_bmo,
    "harvest": parse_harvest,
    "evolve": parse_evolve,
    "globalx_us": parse_globalx_us,
    "jpmorgan_xls": parse_jpmorgan_xls,
    "neos_csv": parse_neos_csv,
    "amplify_rendered": parse_amplify_rendered,
    "globalx_ca_rendered": parse_globalx_ca_rendered,
    "purpose_single": parse_purpose_single,
}


# ---------------------------------------------------------------------------
# 3. FETCH + ORCHESTRATION
# ---------------------------------------------------------------------------

def fetch(url: str) -> str:
    """One retry with the other header set on a refusal. Issuers disagree about
    which requests they like, and the disagreement shows up as 403/406/429, so
    trying the other identity once is cheaper than maintaining a perfect map."""
    resp = requests.get(url, headers=ACTIVE_HEADERS, timeout=REQUEST_TIMEOUT)
    if resp.status_code in (401, 403, 406, 429, 503):
        other = LEGACY_HEADERS if ACTIVE_HEADERS is REQUEST_HEADERS else REQUEST_HEADERS
        log.info("  -> %s on %s, retrying with the other header set",
                 resp.status_code, url)
        time.sleep(1.0)
        resp = requests.get(url, headers=other, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def fetch_binary(url: str) -> str:
    """For endpoints that return a binary file (e.g. JPMorgan's .xlsx export).
    Returns the raw bytes decoded as latin-1 (a lossless 1:1 byte mapping),
    so the bytes can be re-encoded exactly by the parser and every parser
    can keep the same str-in/dict-out signature."""
    resp = requests.get(url, headers=ACTIVE_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.content.decode("latin-1")

def fetch_rendered(url: str, wait_selector: str = None, wait_ms: int = 6000) -> str:
    """For pages that only populate their holdings table via client-side JS
    (Amplify's Firestore-backed holdings pages, Global X Canada's Holdings
    tab). Uses a headless Chromium via Playwright, waits for either a given
    CSS selector to appear or a flat delay, then returns the fully-rendered
    page HTML, which the matching parser then reads with BeautifulSoup
    exactly like a normal static fetch."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=ACTIVE_HEADERS["User-Agent"])
        try:
            page.goto(url, timeout=REQUEST_TIMEOUT * 1000, wait_until="domcontentloaded")
            if wait_selector:
                page.wait_for_selector(wait_selector, timeout=wait_ms)
            else:
                page.wait_for_timeout(wait_ms)
            return page.content()
        finally:
            browser.close()




def describe_response(html) -> str:
    """When a parser can't find what it expects, the useful question is what the
    server actually sent. A bot-challenge page, a consent wall and a genuinely
    restructured page all look identical to a selector that returns None, so log
    enough of the body to tell them apart on the next run."""
    if html is None:
        return "no response body — the fetch itself failed"
    try:
        soup = BeautifulSoup(html, "lxml")
        title = soup.title.get_text(strip=True) if soup.title else "(no <title>)"
        tables = len(soup.find_all("table"))
        table_ids = [t.get("id") or t.get("class") or "(unnamed)"
                     for t in soup.find_all("table")[:5]]
        text = " ".join(soup.get_text(" ").split())[:180]
        return (f"body was {len(html)} chars, title={title!r}, {tables} table(s) "
                f"{table_ids}, text starts: {text!r}")
    except Exception:  # noqa: BLE001 — diagnostics must never mask the real error
        return f"body was {len(html)} chars, could not be parsed for diagnostics"


DATE_RE = re.compile(r"(20\d{2})[/\-](\d{1,2})[/\-](\d{1,2})|(\d{1,2})/(\d{1,2})/(20\d{2})")
AMOUNT_RE = re.compile(r"\$\s?([\d,]+\.\d{2,6})")


def _iso_date(text: str):
    m = DATE_RE.search(text or "")
    if not m:
        return None
    if m.group(1):
        y, mo, d = m.group(1), m.group(2), m.group(3)
    else:
        mo, d, y = m.group(4), m.group(5), m.group(6)
    try:
        return "%04d-%02d-%02d" % (int(y), int(mo), int(d))
    except ValueError:
        return None


def parse_distributions(html: str) -> list:
    """Pull distribution history out of whatever table the issuer put it in.

    Issuers vary wildly: Harvest splits history across a dozen per-year tables
    (tablepress-hhl_distributions, -no-2, -no-3 ...), Hamilton uses a single
    table, and column order differs everywhere. So rather than per-issuer
    selectors, find any table whose header mentions a distribution-ish date and
    an amount, then read columns by header name.

    Returns newest-first [{ex_date, pay_date, amount, frequency}], de-duplicated
    on ex_date, capped at 60 rows (five years of monthly payers) so a fund with
    a decade of history doesn't bloat funds.json.
    """
    soup = BeautifulSoup(html, "lxml")
    rows_out = {}

    for table in soup.find_all("table"):
        head_cells = table.find("tr")
        if not head_cells:
            continue
        headers = [c.get_text(" ", strip=True).lower()
                   for c in head_cells.find_all(["th", "td"])]
        joined = " ".join(headers)
        if not any(k in joined for k in ("ex-dividend", "ex dividend", "ex-div",
                                         "ex-distribution", "ex date")):
            continue
        if not any(k in joined for k in ("amount", "cash", "distribution", "class a", "per unit", "$")):
            continue

        def col(*names):
            for i, h in enumerate(headers):
                if any(nm in h for nm in names):
                    return i
            return None

        i_ex = col("ex-dividend", "ex dividend", "ex-div", "ex-distribution", "ex date")
        i_pay = col("payment date", "pay date", "payable")
        i_amt = col("class a", "amount", "per unit", "cash distribution", "amount ($)")
        i_freq = col("frequency")

        for tr in table.find_all("tr")[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
            if not cells or i_ex is None or i_ex >= len(cells):
                continue
            ex = _iso_date(cells[i_ex])
            if not ex:
                continue
            amt = None
            if i_amt is not None and i_amt < len(cells):
                m = AMOUNT_RE.search(cells[i_amt])
                if m:
                    amt = float(m.group(1).replace(",", ""))
            if amt is None:  # fall back to the first money-looking cell
                for c in cells:
                    m = AMOUNT_RE.search(c)
                    if m:
                        amt = float(m.group(1).replace(",", ""))
                        break
            if amt is None:
                continue
            rec = {"ex_date": ex, "amount": round(amt, 6)}
            pay = _iso_date(cells[i_pay]) if (i_pay is not None and i_pay < len(cells)) else None
            if pay:
                rec["pay_date"] = pay
            if i_freq is not None and i_freq < len(cells) and cells[i_freq]:
                rec["frequency"] = cells[i_freq]
            rows_out.setdefault(ex, rec)   # first table wins on duplicates

    out = sorted(rows_out.values(), key=lambda r: r["ex_date"], reverse=True)
    return out[:60]


def distribution_summary(dists: list) -> dict:
    """Trailing-12-month total and the latest payment — the two numbers an
    income investor actually looks at. Deliberately NOT a yield: that needs a
    price, and dividing by NAV would silently produce a different figure from
    the issuer's own published yield."""
    if not dists:
        return {}
    latest = dists[0]
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=365)).isoformat()
    ttm = [d["amount"] for d in dists if d["ex_date"] >= cutoff]
    out = {
        "last_amount": latest["amount"],
        "last_ex_date": latest["ex_date"],
        "count": len(dists),
    }
    if latest.get("frequency"):
        out["frequency"] = latest["frequency"]
    if ttm:
        out["ttm_total"] = round(sum(ttm), 4)
        out["ttm_payments"] = len(ttm)
    return out


DH_BASE = "https://dividendhistory.org/payout/"
DH_ATTRIBUTION = "dividendhistory.org"


def dividendhistory_urls(fund: Fund) -> list:
    """Most Canadian listings sit under /payout/tsx/, but not all — TECY is a
    Canadian fund filed under the bare path, and guessing from region alone
    silently loses it. Try the likely shape first, then the other."""
    t = fund.ticker.upper()
    tsx = f"{DH_BASE}tsx/{t}/"
    plain = f"{DH_BASE}{t}/"
    return [tsx, plain] if fund.region == "CAD" else [plain, tsx]


def parse_dividendhistory(html: str) -> list:
    """Distribution history from dividendhistory.org.

    Their table leads with FUTURE rows flagged 'unconfirmed/estimated' — for
    HMAX that was two projected payments dated after today. Ingesting those
    would inflate trailing-twelve-month totals and draw distributions on the
    cadence chart that were never paid, so anything unconfirmed or dated in the
    future is dropped. That rule is deliberate; don't relax it to gain rows.
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="dividend-table") or soup.find("table")
    if not table:
        return []

    today = datetime.now(timezone.utc).date().isoformat()
    out = []
    for tr in table.find_all("tr")[1:]:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        if len(cells) < 3:
            continue
        ex = _iso_date(cells[0])
        if not ex or ex > today:
            continue                                   # not paid yet
        status = cells[3].lower() if len(cells) > 3 else ""
        if "unconfirm" in status or "estimat" in status:
            continue                                   # a projection, not a payment
        m = AMOUNT_RE.search(cells[2])
        if not m:
            continue
        rec = {"ex_date": ex,
               "amount": round(float(m.group(1).replace(",", "")), 6),
               "source": DH_ATTRIBUTION}
        pay = _iso_date(cells[1])
        if pay:
            rec["pay_date"] = pay
        out.append(rec)

    out.sort(key=lambda r: r["ex_date"], reverse=True)
    return out[:60]


def fetch_dividendhistory(fund: Fund) -> list:
    """Fallback only. Issuer-published history always wins, because it is the
    primary record; this fills funds whose issuer publishes nothing parseable."""
    for url in dividendhistory_urls(fund):
        try:
            log.info("  -> distributions fallback %s", url)
            html = fetch(url)
            time.sleep(DELAY_BETWEEN_REQUESTS)
            rows = parse_dividendhistory(html)
            if rows:
                log.info("  -> %d distributions from %s, latest %s",
                         len(rows), DH_ATTRIBUTION, rows[0]["ex_date"])
                return rows
            log.info("  -> no usable rows at %s", url)
        except Exception as exc:  # noqa: BLE001
            log.info("  -> %s: %s", url, exc)
    log.warning("  -> no distributions found anywhere for %s", fund.ticker)
    return []


def profile_html(fund: Fund, holdings_html: str) -> str:
    """The page carrying key facts AND distribution history.

    For most issuers that's the same page we just fetched for holdings. NEOS and
    Amplify are the exceptions: their holdings arrive as a CSV / separate URL, so
    their fund page has to be fetched once — and it is that page, not the CSV,
    that holds the distribution tables. Fetch it once and reuse for both.
    """
    if fund.parser not in STATS_SOURCES:
        return holdings_html
    source = STATS_SOURCES[fund.parser]
    if source is None:
        return holdings_html
    url = source(fund)
    log.info("  -> profile page %s", url)
    html = fetch(url)
    time.sleep(DELAY_BETWEEN_REQUESTS)
    return html


def collect_stats(fund: Fund, page_html: str) -> dict:
    """Never fatal: a stats failure leaves holdings intact and logs a warning,
    because a fund with holdings and no AUM is still useful."""
    if fund.parser not in STATS_SOURCES:
        return {}
    try:
        stats = parse_fund_stats(page_html)
        if not stats:
            log.info("  -> no key facts found for %s", fund.ticker)
        return stats
    except Exception as exc:  # noqa: BLE001
        log.warning("  -> stats FAILED for %s: %s", fund.ticker, exc)
        return {}


def load_previous(path: Path = OUTPUT_PATH) -> dict:
    """The previous run's output, used to carry a fund forward when today's
    fetch fails. An issuer blocking us for a day is not the same event as a
    fund ceasing to exist, and the site shouldn't render them identically."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not read previous %s: %s", path, exc)
        return {}


def carry_forward(fund: Fund, previous: dict) -> None:
    """Keep the last good holdings/stats and mark them stale, so the fund page
    shows real numbers with an honest 'as of' date instead of going blank."""
    prev = previous.get(fund.ticker)
    if not prev or not prev.get("holdings"):
        return
    fund.holdings = prev.get("holdings", {})
    fund.stats = prev.get("stats", {}) or {}
    fund.distributions = prev.get("distributions", []) or []
    fund.as_of = prev.get("as_of", "") or prev.get("last_seen", "")
    fund.stale = True
    log.info("  -> carrying forward %d holdings from %s",
             len(fund.holdings), fund.as_of or "an earlier run")


def run(registry: list[Fund]) -> list[Fund]:
    previous = load_previous()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for fund in registry:
        log.info("Fetching %s (%s) from %s", fund.ticker, fund.issuer, fund.holdings_url)
        html = None
        global ACTIVE_HEADERS
        ACTIVE_HEADERS = HEADERS_BY_PARSER.get(fund.parser, REQUEST_HEADERS)
        try:
            if fund.parser == "jpmorgan_xls":
                html = fetch_binary(fund.holdings_url)
            elif fund.needs_browser:
                html = fetch_rendered(fund.holdings_url)
            else:
                html = fetch(fund.holdings_url)
            parser = PARSERS[fund.parser]
            fund.holdings = parser(html)
            fund.fetched_ok = bool(fund.holdings)
            if fund.fetched_ok:
                fund.as_of = today
                fund.stale = False
                page = profile_html(fund, html)
                fund.stats = collect_stats(fund, page)
                try:
                    fund.distributions = parse_distributions(page)
                    if not fund.distributions and page is not html:
                        fund.distributions = parse_distributions(html)
                    for _d in fund.distributions:
                        _d.setdefault("source", "issuer")
                    if not fund.distributions:
                        fund.distributions = fetch_dividendhistory(fund)
                    if fund.distributions:
                        fund.stats["distribution_source"] = fund.distributions[0].get("source", "issuer")
                        fund.stats.update(distribution_summary(fund.distributions))
                        log.info("  -> %d distributions, latest %s",
                                 len(fund.distributions), fund.distributions[0]["ex_date"])
                except Exception as exc:  # noqa: BLE001
                    log.warning("  -> distributions FAILED: %s", exc)
            else:
                fund.error = "parser ran but returned no holdings"
                carry_forward(fund, previous)
        except Exception as exc:  # noqa: BLE001 — log and continue, don't kill the whole run
            fund.fetched_ok = False
            fund.error = str(exc)
            log.warning("  -> FAILED: %s", exc)
            log.warning("  -> %s", describe_response(html))
            carry_forward(fund, previous)

        # A blocked issuer throws before the distribution step above ever runs,
        # so try the fallback out here too — Evolve's holdings 403 shouldn't also
        # cost us their payment history, which is public elsewhere.
        if not fund.distributions:
            fund.distributions = fetch_dividendhistory(fund)
            if fund.distributions:
                fund.stats["distribution_source"] = fund.distributions[0].get("source", "issuer")
                fund.stats.update(distribution_summary(fund.distributions))
        time.sleep(DELAY_BETWEEN_REQUESTS)
    return registry


def attach_price_and_yield(registry: list) -> None:
    """Give every fund the same yield measure.

    Issuers publish yields on incompatible bases — a 30-day SEC yield, an
    annualised distribution yield and a trailing twelve-month yield are three
    different numbers, and only 86 of 120 funds publish any at all. We keep the
    issuer's figure (labelled, on the fund page) but also compute one
    comparable number for everyone: twelve months of actual distributions over
    the latest close. Prices come from data/prices, which covers all 120.
    """
    price_dir = Path("data/prices")
    if not price_dir.exists():
        log.warning("no price files — skipping yield computation")
        return
    done = 0
    for fund in registry:
        csv_path = price_dir / f"{fund.ticker}.csv"
        if not csv_path.exists():
            continue
        try:
            last = csv_path.read_text().strip().splitlines()[-1]
            day, close = last.split(",")[0], float(last.split(",")[1])
        except Exception:  # noqa: BLE001
            continue
        if close <= 0:
            continue
        fund.stats["price"] = round(close, 4)
        fund.stats["price_date"] = day
        ttm = fund.stats.get("ttm_total")
        if ttm:
            fund.stats["yield_ttm"] = round(ttm / close * 100, 2)
            done += 1
    log.info("Computed a trailing-12-month yield for %d funds", done)


def write_output(registry: list[Fund], path: Path = OUTPUT_PATH,
                 merge: bool = False) -> None:
    """When only part of the registry was scraped (--only), merge into the
    existing file instead of replacing it. Writing a filtered run straight out
    would silently delete every fund we didn't ask for."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {}
    if merge and path.exists():
        try:
            payload = json.loads(path.read_text())
            log.info("Merging %d scraped funds into the existing %d in %s",
                     len(registry), len(payload), path)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not read existing %s (%s) — writing fresh", path, exc)
            payload = {}

    for fund in registry:
        payload[fund.ticker] = {
            "name": fund.name,
            "issuer": fund.issuer,
            "region": fund.region,
            "holdings": fund.holdings,
            "stats": fund.stats,
            "distributions": fund.distributions,
            "as_of": fund.as_of,
            "stale": fund.stale,
            "fetched_ok": fund.fetched_ok,
            "error": fund.error,
        }
    path.write_text(json.dumps(payload, indent=2))
    ok = sum(1 for f in registry if f.fetched_ok)
    with_aum = sum(1 for f in registry if f.stats.get("aum_musd"))
    with_dist = sum(1 for f in registry if f.distributions)
    carried = [f.ticker for f in registry if f.stale and f.holdings]
    empty = [f.ticker for f in registry if not f.holdings]
    if carried:
        log.warning("Carried forward (issuer unreachable today): %s", ", ".join(carried))
    if empty:
        log.warning("No data at all: %s", ", ".join(empty))
    log.info("Wrote %s — %d/%d fetched live, %d carried forward, %d with AUM, %d with distributions",
             path, ok, len(registry), len(carried), with_aum, with_dist)


def select(registry: list[Fund], only: str) -> list[Fund]:
    """--only accepts tickers, issuer names or parser keys, comma separated and
    case-insensitive: --only=evolve,hamilton / --only=HMAX,BANK. Verifying a
    one-issuer fix shouldn't mean re-scraping 120 funds across every issuer."""
    wanted = {w.strip().lower() for w in only.split(",") if w.strip()}
    picked = [f for f in registry
              if f.ticker.lower() in wanted
              or f.parser.lower() in wanted
              or f.issuer.lower() in wanted
              or any(w in f.issuer.lower() for w in wanted)]
    missing = wanted - {f.ticker.lower() for f in picked} \
                     - {f.parser.lower() for f in picked} \
                     - {f.issuer.lower() for f in picked}
    unmatched = [w for w in missing
                 if not any(w in f.issuer.lower() for f in picked)]
    if unmatched:
        log.warning("--only had no match for: %s", ", ".join(sorted(unmatched)))
    return picked


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", default="",
                    help="comma-separated tickers, issuers or parser keys to scrape")
    args = ap.parse_args()

    registry = FUND_REGISTRY
    filtered = bool(args.only)
    if filtered:
        registry = select(registry, args.only)
        if not registry:
            raise SystemExit(f"--only={args.only!r} matched no funds")
        log.info("Scraping %d of %d funds: %s", len(registry), len(FUND_REGISTRY),
                 ", ".join(f.ticker for f in registry))

    results = run(registry)
    attach_price_and_yield(results)
    write_output(results, merge=filtered)



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
