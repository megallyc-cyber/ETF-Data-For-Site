"""Rebuild the fund pages from the data already on disk.

The 288 pages were stamped out of the old template, which read the ticker
only from a query string \u2014 so every /fund/TICKER/ page looked up an empty
ticker and said it could not find the fund. The template is fixed now, and
there is no need to scrape every issuer again to reprint them.
"""
import html as _h
import json, re, subprocess
from pathlib import Path

template = Path("fund/index.html").read_text()
data = json.loads(Path("data/funds.json").read_text())
rows = data.get("funds") if isinstance(data, dict) else data
if isinstance(rows, dict):
    rows = list(rows.values())

def num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(re.sub(r"[^0-9.\\-]", "", str(v)))
    except ValueError:
        return None

written = 0
for f in rows:
    t = str(f.get("ticker") or "").upper()
    if not t or not re.match(r"^[A-Z0-9.\\-]{1,8}$", t):
        continue
    st = f.get("stats") or {}
    name = f.get("name") or t
    issuer = f.get("issuer") or ""
    y = num(st.get("yield_ttm")) or num(st.get("yield"))
    price = num(st.get("price")) or num(st.get("nav"))
    ttm = num(st.get("ttm_total"))

    bits = [name]
    if y is not None:
        bits.append("yielding %.1f%%" % y)
    if ttm is not None:
        bits.append("paid $%.4f a share over twelve months" % ttm)
    if issuer:
        bits.append("from " + issuer)
    desc = (t + ": " + ", ".join(bits) +
            ". Holdings, distributions and fund size, taken from the issuer.")[:300]
    title = "%s \u2014 %s | Licentia" % (t, name)
    url = "https://licentia.ca/fund/%s" % t

    facts = []
    if y is not None:
        facts.append("<li>Distribution yield: <b>%.1f%%</b></li>" % y)
    if ttm is not None:
        facts.append("<li>Paid per share, twelve months: <b>$%.4f</b></li>" % ttm)
    if price is not None:
        facts.append("<li>Unit price: <b>$%.2f</b></li>" % price)
    if issuer:
        facts.append("<li>Manager: <b>%s</b></li>" % _h.escape(issuer))
    holds = f.get("holdings") or {}
    if holds:
        facts.append("<li>Positions held: <b>%d</b></li>" % len(holds))

    hide = ("position:absolute;width:1px;height:1px;overflow:hidden;"
            "clip:rect(0 0 0 0);white-space:nowrap")
    summary = ('<div id="seo-summary" style="' + hide + '">'
               + "<h1>" + _h.escape(t) + " \u2014 " + _h.escape(name) + "</h1>"
               + "<p>" + _h.escape(desc) + "</p>"
               + ("<ul>" + "".join(facts) + "</ul>" if facts else "")
               + "</div>")

    ld = {"@context": "https://schema.org", "@type": "FinancialProduct",
          "name": "%s \u2014 %s" % (t, name), "tickerSymbol": t,
          "url": url, "description": desc}
    if issuer:
        ld["provider"] = {"@type": "Organization", "name": issuer}

    page = template
    page = re.sub(r"<title>[^<]*</title>",
                  "<title>" + _h.escape(title) + "</title>", page, count=1)
    page = re.sub(r'<meta name="description" content="[^"]*">',
                  '<meta name="description" content="' + _h.escape(desc, quote=True) + '">',
                  page, count=1)
    page = re.sub(r'<link rel="canonical"[^>]*>', "", page)
    page = page.replace("</head>",
        '<link rel="canonical" href="' + url + '">' + chr(10) + "</head>", 1)
    page = page.replace("</head>",
        '<script type="application/ld+json">' + json.dumps(ld) + "</" + "script>"
        + chr(10) + "</head>", 1)
    page = page.replace("<body>",
        "<body>" + chr(10) + summary + chr(10)
        + '<script>window.__TICKER = "' + t + '";</' + "script>", 1)

    out = Path("fund") / t
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page)
    written += 1

report = {"pagesWritten": written, "fundsSeen": len(rows)}
Path("data").mkdir(exist_ok=True)
Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "-A"], check=False)
subprocess.run(["git", "commit", "-m", "Reprint the fund pages from the fixed template"], check=False)
subprocess.run(["git", "push"], check=False)