"""
Probe what the free Twelve Data / FMP tiers actually return for OUR funds.

Catalog presence is not data access: Twelve Data lists all 120 of our tickers,
but international coverage is gated by plan tier, so the only way to know what
the free key serves is to ask it. This writes data/api-probe.json (committed, so
it can be read without fighting the Actions log viewer) and a run summary.

Deliberately small: a stratified sample, not all 120. The free tier allows
8 credits/minute, so a full sweep would take ~15 minutes to answer a question a
16-symbol sample answers in two.
"""
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TD_KEY = os.environ.get("TWELVEDATA_API_KEY", "").strip()
FMP_KEY = os.environ.get("FMP_API_KEY", "").strip()
FUNDS = Path("data/funds.json")
OUT = Path("data/api-probe.json")
PAUSE = 8.5  # free tier is 8 credits/minute


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "ledger-etf/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as exc:  # noqa: BLE001
        return {"_error": str(exc)}


def redact(text: str) -> str:
    """Never let a key reach the committed file or the log."""
    for k in (TD_KEY, FMP_KEY):
        if k:
            text = text.replace(k, "***")
    return text


def sample(funds: dict, n_per_group: int = 5) -> list:
    """A few funds from each listing venue, since that's the axis we expect
    coverage to break along."""
    groups = {"TSX": [], "NEO": [], "US": []}
    for t, v in funds.items():
        if not v.get("holdings"):
            continue
        region = v.get("region")
        # Purpose single-stock Yield Shares are NEO-listed despite US underlyings
        venue = "US" if region == "US" and not t.startswith("Y") else ("NEO" if region == "US" else "TSX")
        if len(groups[venue]) < n_per_group:
            groups[venue].append(t)
    return [(t, g) for g, ts in groups.items() for t in ts]


def probe_twelvedata(picks: list) -> dict:
    if not TD_KEY:
        return {"status": "no key in environment"}
    results, ok = {}, 0
    for ticker, venue in picks:
        mic = {"TSX": "XTSE", "NEO": "NEOE", "US": ""}[venue]
        q = {"symbol": ticker, "apikey": TD_KEY}
        if mic:
            q["mic_code"] = mic
        d = get("https://api.twelvedata.com/quote?" + urllib.parse.urlencode(q))
        if d.get("close") or d.get("previous_close"):
            ok += 1
            results[ticker] = {"venue": venue, "ok": True,
                               "close": d.get("close"), "currency": d.get("currency"),
                               "name": d.get("name")}
        else:
            msg = d.get("message") or d.get("_error") or str(list(d)[:4])
            results[ticker] = {"venue": venue, "ok": False, "why": redact(str(msg))[:200]}
        time.sleep(PAUSE)
    # one dividend probe — distribution history is the field we most want
    div = {}
    for ticker, venue in picks[:1] + picks[-1:]:
        mic = {"TSX": "XTSE", "NEO": "NEOE", "US": ""}[venue]
        q = {"symbol": ticker, "apikey": TD_KEY, "range": "last"}
        if mic:
            q["mic_code"] = mic
        d = get("https://api.twelvedata.com/dividends?" + urllib.parse.urlencode(q))
        div[ticker] = redact(json.dumps(d))[:300]
        time.sleep(PAUSE)
    return {"quotes_ok": ok, "quotes_tried": len(picks), "detail": results, "dividends": div}


def probe_fmp(picks: list) -> dict:
    if not FMP_KEY:
        return {"status": "no key in environment"}
    out = {}
    for ticker, venue in picks:
        sym = ticker if venue == "US" else ticker + ".TO"
        d = get(f"https://financialmodelingprep.com/api/v3/quote/{sym}?apikey={FMP_KEY}")
        if isinstance(d, list) and d:
            out[sym] = {"ok": True, "price": d[0].get("price"), "name": d[0].get("name")}
        else:
            out[sym] = {"ok": False, "why": redact(json.dumps(d))[:160]}
        time.sleep(0.4)
    return {"ok": sum(1 for v in out.values() if v.get("ok")), "tried": len(out), "detail": out}


def main() -> None:
    funds = json.loads(FUNDS.read_text())
    picks = sample(funds)
    report = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sampled": [f"{t} ({v})" for t, v in picks],
        "twelvedata": probe_twelvedata(picks),
        "fmp": probe_fmp(picks),
    }
    OUT.write_text(json.dumps(report, indent=2))

    td, fmp = report["twelvedata"], report["fmp"]
    lines = ["## API probe", ""]
    lines.append(f"- Twelve Data quotes: **{td.get('quotes_ok','?')}/{td.get('quotes_tried','?')}**")
    lines.append(f"- FMP quotes: **{fmp.get('ok','?')}/{fmp.get('tried','?')}**")
    lines.append("")
    lines.append("| ticker | venue | TD | detail |")
    lines.append("|---|---|---|---|")
    for t, v in (td.get("detail") or {}).items():
        mark = "yes" if v.get("ok") else "no"
        info = v.get("close") or v.get("why", "")
        lines.append(f"| {t} | {v.get('venue')} | {mark} | {str(info)[:70]} |")
    summary = "\n".join(lines)
    print(summary)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as fh:
            fh.write(summary + "\n")


if __name__ == "__main__":
    main()
