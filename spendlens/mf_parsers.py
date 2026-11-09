"""Fixed parsers for AMC factsheet layouts that are regular enough to read without AI. Each returns one fund object in
the extracted-factsheet format of mf.py (printed numbers only; None when not printed) plus a report of what it found,
so the result can be checked. The mf-factsheet-analyst agent remains the fallback for layouts not listed here.

    python spendlens/mf_extract.py factsheet <pdf> --amc axis --scheme "Axis Small Cap Fund" --amfi 125354 --write

Axis (since 2025): an index on pages 2-3, one page per equity scheme. The scheme page holds the month-end AUM, the
3-year statistical measures, turnover, market-cap split, the managers (with "managing the scheme since" dates in the
performance footnote), Direct-plan returns against the benchmark, and the whole portfolio in a right-hand column
(name | industry | % of NAV, industries wrapping onto a second line). The Direct plan's total expense ratio is in the
"Expense Ratio" section near the back (Base: Regular, Direct, Retail | Total: Regular, Direct, Retail).
"""
import re
from datetime import datetime

import mf_extract as mx

# portfolio section headers (they carry the section's total, not a holding); anything else in capitals is a line,
# e.g. "NIFTY" (an index derivative position)
SECTION = re.compile(r"^(EQUITY|DEBT|DEBT SECURITIES|MONEY MARKET|MONEY MARKET INSTRUMENTS|GOVERNMENT|CORPORATE BONDS?|"
                     r"REITS?|INVITS?|MUTUAL FUND UNITS|EXCHANGE TRADED FUNDS?|DERIVATIVES?|"
                     r"FOREIGN (EQUITY|SECURITIES)|CASH|NET CURRENT ASSETS)(\s*[&/,].*)?$")
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}


def _date(day, month, year):
    """"30", "September" / "Sep" / "Sept", "2026" -> "2026-09-30"."""
    mon = next((n for name, n in MONTHS.items() if name.startswith(month.lower()[:3])), None) if month else None
    try:
        return datetime(int(year), mon, int(day)).date().isoformat() if mon else None
    except (TypeError, ValueError):
        return None


def _num(s):
    try:
        return float(s.replace(",", ""))
    except (AttributeError, ValueError):
        return None


def _pieces(reader, i):
    """[(y, x, text)] of page i, positions in page space (y up)."""
    out = []

    def visit(t, cm, tm, _fd, _fs):
        if t.strip():
            out.append((tm[4] * cm[1] + tm[5] * cm[3] + cm[5], tm[4] * cm[0] + tm[5] * cm[2] + cm[4], t.strip()))
    reader.pages[i].extract_text(visitor_text=visit)
    return out


def _axis_holdings(pieces, width):
    """The portfolio column: rows with a name (x from 60% of the width) and a % of NAV at the right edge; industry
    fragments between them belong to the nearest row (they wrap above and below it)."""
    name_x0, ind_x0, pct_x0 = width * 0.60, width * 0.79, width * 0.90
    rows = {}
    frags = []
    for y, x, t in pieces:
        if x >= pct_x0 and re.fullmatch(r"-?\d+(\.\d+)?%", t):
            rows.setdefault(round(y, 1), {"y": y, "name": [], "pct": None})["pct"] = float(t[:-1])
    ys = sorted(rows)
    for y, x, t in pieces:
        if name_x0 <= x < ind_x0:
            k = min(ys, key=lambda r: abs(r - y)) if ys else None
            if k is not None and abs(k - y) < 1.5:
                rows[k]["name"].append((x, t))
            else:
                frags.append(("name", y, x, t))
        elif ind_x0 <= x < pct_x0:
            frags.append(("ind", y, x, t))
    out = []
    for k in sorted(rows, reverse=True):
        r = rows[k]
        out.append({"y": r["y"], "own": bool(r["name"]), "name": [(-r["y"], x, t) for x, t in r["name"]], "pct": r["pct"], "ind": []})
    for kind, y, x, t in frags:
        if not out:
            break
        near = min(out, key=lambda r: abs(r["y"] - y))
        if abs(near["y"] - y) > 7:
            continue
        if kind == "ind":
            near["ind"].append((-y, x, t))
        elif not near["own"] or y < near["y"]:
            # a long name wrapping onto the next line; or one printed around its % line (above and below it)
            near["name"].append((-y, x, t))
    for r in out:
        r["name"] = " ".join(t for _, _, t in sorted(r["name"])).strip()
    lines, skipped = [], []
    for r in out:
        ind = " ".join(t for _, _, t in sorted(r["ind"])).strip()
        if not r["name"] or r["pct"] is None:
            continue
        if SECTION.match(r["name"]) or re.match(r"^(grand |sub ?)?total\b", r["name"], re.I):
            skipped.append(f"{r['name']} {r['pct']}%")     # section headers (EQUITY 90.32%) and totals
            continue
        lines.append({"name": r["name"], "isin": "", "pct": r["pct"], "qty": None, "sector": ind, "rating": ""})
    return lines, skipped


def _axis_ter(reader, scheme):
    """Direct-plan total expense ratio from the Expense Ratio section (last 40% of the pages only)."""
    rx = re.compile(re.escape(scheme) + r"\s+((?:\d+\.\d+%?\s+){1,5}\d+\.\d+%?)")   # some months print a % sign
    n = len(reader.pages)
    for i in range(int(n * 0.6), n):
        t = reader.pages[i].extract_text() or ""
        if "expense" not in t[:600].lower():
            continue
        m = rx.search(t)
        if m:
            vals = [float(v.rstrip("%")) for v in m.group(1).split()]
            # with a Base section: Base (Regular, Direct[, Retail]) then Total (...); without: Total (Regular, Direct[, Retail])
            total = vals[len(vals) // 2:] if re.search(r"base", t[:600], re.I) else vals
            return (total[1] if len(total) > 1 else None), i + 1, vals
    return None, None, None


def parse_axis(pdf, scheme, amfi_code="", category=""):
    loc = mx.locate(pdf, re.escape(scheme))
    if not loc["ranges"]:
        raise SystemExit(f"{pdf}: {scheme} not found (method {loc['method']})")
    page = loc["ranges"][0]["from"]
    reader = mx._reader(pdf)
    width = float(reader.pages[page - 1].mediabox.width)
    pieces = _pieces(reader, page - 1)
    lines, skipped = _axis_holdings(pieces, width)
    text = mx.text(pdf, str(page), max_chars=10 ** 6)
    flat = re.sub(r"\s+", " ", text)
    # the left column alone (the portfolio column interleaves with it line by line), spaces removed: for the
    # managers footnote "...TejasShethismanagingtheschemesince13thMay2024..."
    left = [(y, x, t) for y, x, t in pieces if x < width * 0.60]
    glued = re.sub(r"\s+", "", "".join(t for _, _, t in sorted(left, key=lambda p: (-round(p[0], 0), p[1]))))
    left_flat = re.sub(r"\s+", " ", " ".join(t for _, _, t in sorted(left, key=lambda p: (-round(p[0], 0), p[1]))))

    m = re.search(r"AS ON\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})", flat)
    as_on = _date(*m.groups()) if m else None
    aums = re.findall(r"([\d,]+\.\d+)\s*Cr", flat)
    # the monthly average is printed first, the month-end figure ("AUM AS ON ...") second
    aum = _num(aums[1]) if len(aums) > 1 else (_num(aums[0]) if aums else None)

    def grab(pattern):
        mm = re.search(pattern, flat, re.I)
        return _num(mm.group(1)) if mm else None
    std = grab(r"Standard Deviation\s*-?\s*(\d+(?:\.\d+)?)%")
    beta = grab(r"Beta\s*-?\s*(\d+(?:\.\d+)?)")
    sharpe = grab(r"Sharpe Ratio\**\s*-?\s*(-?\d+(?:\.\d+)?)")
    times = grab(r"(\d+(?:\.\d+)?)\s*times")
    cap = {k: grab(rf"{label}:\s*(\d+(?:\.\d+)?)%") for k, label in (("large", "Large Cap"), ("mid", "Mid Cap"), ("small", "Small Cap"))}
    cash = grab(r"Cash\s*&\s*Others:\s*(-?\d+(?:\.\d+)?)%")
    bm = re.search(r"BENCHMARK\s+(.+?TRI)", flat)

    # "<label> [Growth Option] [-]9.86% 10,986 [-]13.92% 14,793 ...": a minus may stand apart from its number once
    # the column is rebuilt by position, and "Direct Plan -" carries a separator dash of its own
    pair = r"(-\s?)?(\d+\.\d+)%\s+[\d,]+"

    def signed(mm, k):
        return None if mm.group(2 * k) is None else (-1 if mm.group(2 * k - 1) else 1) * float(mm.group(2 * k))

    def returns(text, label):
        mm = re.search(label + r"\s*(?:Growth Option\s*)?" + pair + r"(?:\s+" + pair + r")?(?:\s+" + pair + r")?", text)
        return ({"1y": signed(mm, 1), "3y": signed(mm, 2), "5y": signed(mm, 3)} if mm else None), mm
    direct, dm = returns(left_flat, r"Direct Plan\s*-")
    bench = returns(left_flat[dm.end():], r"\(Benchmark\)")[0] if dm else None

    managers = []
    # the footnote, spaces gone: "...structure.TejasShethismanagingtheschemesince13thMay2024...&KrishnaaNismanaging..."
    for nm, d, mo, y in re.findall(r"(?:^|[.&,])([A-Z][a-z]+(?:[A-Z][a-z]*)+?)ismanagingtheschemesince(\d{1,2})(?:st|nd|rd|th)([A-Za-z]+?)(\d{4})", glued):
        managers.append({"name": re.sub(r"(?<=[a-z])(?=[A-Z])", " ", nm).strip(), "since": _date(d, mo, y) or ""})

    ter, ter_page, ter_vals = _axis_ter(reader, scheme)
    fund = {
        "scheme": scheme, "plan": "Direct", "amfi_code": amfi_code, "category": category,
        "benchmark": bm.group(1).strip() if bm else "",
        "aum_cr": aum, "ter_pct": ter, "std_dev": std, "beta": beta, "sharpe": sharpe, "alpha": None, "treynor": None,
        "turnover_pct": round(times * 100, 2) if times is not None else None,
        "top10_pct": None, "cash_pct": cash, "cap_mix": cap,
        "returns": direct or {}, "benchmark_returns": bench or {},
        "managers": managers, "holdings": lines,
        "notes": (f"Parsed from the Axis scheme page {page} (fixed parser). Turnover printed as {times} times. "
                  f"TER: Direct total expense ratio from page {ter_page} {ter_vals}. Holdings have no ISIN or share counts "
                  "in the factsheet, so the buying trend compares weights.") if ter_page else
                 f"Parsed from the Axis scheme page {page} (fixed parser). Expense ratio row not found.",
    }
    report = {"page": page, "method": loc["method"], "as_on": as_on, "aum_cr": aum, "ter_direct": ter, "std_dev": std,
              "beta": beta, "sharpe": sharpe, "turnover_pct": fund["turnover_pct"], "cap_mix": cap, "cash_pct": cash,
              "returns": direct, "benchmark_returns": bench, "managers": managers,
              "holdings": len(lines), "holdings_total_pct": round(sum(x["pct"] for x in lines), 2), "skipped_rows": skipped}
    return fund, as_on, report


def parse_edelweiss(pdf, scheme, amfi_code="", category=""):
    """Edelweiss Mutual Fund (since 2025): ~270 pages, three per scheme. Page 1: "Data as on <date>", returns for the
    last 1 / 3 / 5 years (Regular, Direct, Benchmark), AUM and AAUM, base expense ratios (BER) per plan, standard
    deviation / beta / information ratio (1-year basis) and Sharpe (3-year), portfolio turnover, managers in a note,
    and only the top 10 holdings. Page 3: the market-cap split. The full portfolio is in the separate monthly
    disclosure. Files are named by the month they are published, so the date printed on the page decides the month."""
    loc = mx.locate(pdf, re.escape(scheme).replace(r"\ ", r"\s*"))
    if not loc["ranges"]:
        raise SystemExit(f"{pdf}: {scheme} not found (method {loc['method']})")
    rng = loc["ranges"][0]
    first, last = rng["from"], min(rng["to"], rng["from"] + 2)
    reader = mx._reader(pdf)
    pieces = _pieces(reader, first - 1)
    flat = re.sub(r"\s+", " ", mx.text(pdf, f"{first}-{last}", max_chars=10 ** 6))
    plain = re.sub(r"\s+", " ", mx.text(pdf, f"{first}-{last}", max_chars=10 ** 6, plain=True))
    texts = (flat, plain)
    # Three layouts so far: (A) Aug 2026 on: "Data as on August 31, 2026", "Direct Plan: BER 0.41%", "Standard
    # Deviation (%) 17.63"; (B) to Jul 2026: "BER / TER (Direct Plan) : 0.42%/0.72%", "Month End AUM (₹) : 17,769 Cr.",
    # "Standard deviation2,6 : 17.68%", "Top 10 stocks@ : 22.44%"; (C) 2025: "Month End AUM Rs. 10,028.27 Crore",
    # "Total Expense Ratios~: Regular Plan 1.70% Direct Plan 0.40%", "Std. deviation 16.63%", "(As on 31st May, 2025)".

    def find(*patterns):
        for t in texts:
            for p in patterns:
                mm = re.search(p, t, re.I)
                if mm:
                    return mm
        return None

    def grab(*patterns):
        mm = find(*patterns)
        return _num(mm.group(1)) if mm else None

    mon = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
    as_on = None
    mm = find(rf"Dat[ae]\s+as\s+on\s+{mon}\s+(\d{{1,2}}),\s*(\d{{4}})", rf"Holdings\s+as\s+on\s+{mon}\s+(\d{{1,2}}),\s*(\d{{4}})")
    if mm:
        as_on = _date(mm.group(2), mm.group(1), mm.group(3))
    else:
        mm = find(rf"\bas\s+on\s+(\d{{1,2}})(?:st|nd|rd|th)?\s+{mon},?\s*(\d{{4}})")
        if mm:
            as_on = _date(mm.group(1), mm.group(2), mm.group(3))

    def ret(n):   # Regular, Direct, Benchmark -> (Direct, Benchmark)
        mm = find(rf"Returns\s+for\s+last\s+{n}\b.{{0,160}}?(?:Year|years)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)",
                  rf"Direct\s+Benchmark\s+Returns\s*%.{{0,120}}?\b{n}\s+years?\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)(?!\s*%)")
        return (_num(mm.group(2)), _num(mm.group(3))) if mm else (None, None)
    r1, r3, r5 = ret(1), ret(3), ret(5)
    aum = grab(r"(?<![A-Za-z])AUM\s+as\s+on\s+[A-Za-z]+\s+\d{1,2},\s*\d{4}\s*\S?\s*([\d,]+\.\d+)\s*Cr",
               r"Month\s+End\s+AUM\s*(?:\(\S+\)|Rs\.?)?\s*:?\s*([\d,]+(?:\.\d+)?)\s*Cr")
    ter = grab(r"BER\s*/\s*TER\s*\(\s*Direct\s+Plan\s*\)\s*:\s*\d+\.\d+%\s*/\s*(\d+\.\d+)%",
               r"Total\s+Expense\s+Ratios?\W*\d?\s*Regular\s+Plan\s*:?\s*\d+\.\d+%\s*Direct\s+Plan\s*:?\s*(\d+\.\d+)%")
    ber = None
    if ter is None:   # layout A prints only the base expense ratio
        ber = grab(r"Direct\s+Plan:\s*BER\s*(\d+\.\d+)%", r"Changes\s+in\s+Expense\s+Ratio.{0,80}?Direct\s+\d+\.\d+%\s+(\d+\.\d+)%")
    times = grab(r"Equity\s+Turnover\s+(\d+(?:\.\d+)?)", r"Portfolio\s+Turnover\s+Ratio\W*\d?\s*:?\s*(?:Equity\s+)?(\d+\.\d+)")
    cap = {k: grab(rf"{label}\s+(\d+(?:\.\d+)?)%") for k, label in (("large", r"Large\s*Cap"), ("mid", r"Mid\s*Cap"), ("small", r"Small\s*Cap"))}
    words = r"(Midcap|Smallcap|Largecap)"
    mm = find(rf"(\d+\.\d+)%\s+(\d+\.\d+)%\s+(\d+\.\d+)%\s+{words}\s+{words}\s+{words}")
    if mm and (None in cap.values() or sum(cap.values()) < 90):
        cap = {mm.group(i + 4).lower().replace("cap", ""): float(mm.group(i + 1)) for i in range(3)}
    bm = find(r"Benchmark\s+(.+?(?:TRI|Index))")
    printed_top10 = grab(r"Top\s+10\s+stocks\W*:?\s*(\d+\.\d+)%")

    # top 10 holdings (layout A): the box under its label (rank | name | % to net assets)
    lab = next(((y, x) for y, x, t in pieces if t.startswith("Top 10 Holdings")), None)
    holdings = []
    if lab:
        ty, tx = lab
        rows, last_y = {}, ty
        for y, x, t in pieces:
            if ty - 150 < y < ty - 1 and tx - 12 <= x < tx + 200:
                rows.setdefault(round(y, 1), []).append((x, t))
        for y in sorted(rows, reverse=True):
            cells = sorted(rows[y])
            pct = next((float(t[:-1]) for x, t in cells if x >= tx + 150 and re.fullmatch(r"\d+(\.\d+)?%", t)), None)
            name = " ".join(t for x, t in cells if tx + 12 <= x < tx + 150).strip()
            if pct is not None and name:
                holdings.append({"name": name, "isin": "", "pct": pct, "qty": None, "sector": "", "rating": ""})
                last_y = y
            if len(holdings) == 10:
                break
        # the managers note sits in the same middle column, below the box
        note = [(y, x, t) for y, x, t in pieces if tx - 12 <= x < tx + 215 and y < last_y - 2]
        glued = re.sub(r"\s+", "", "".join(t for _, _, t in sorted(note, key=lambda p: (-round(p[0], 0), p[1]))))
    else:
        glued = re.sub(r"\s+", "", plain)
    pat = r"(?:Mr|Ms|Mrs|Dr)\.([A-Z][A-Za-z]+?)\((?i:managingthisfundfrom)([A-Za-z]+)\.?(\d{1,2}),(\d{4})\)"
    managers, seen = [], set()
    for nm, mo, d, y in re.findall(pat, glued) or re.findall(pat, re.sub(r"\s+", "", plain)):
        name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", nm)
        if name not in seen:
            seen.add(name)
            managers.append({"name": name, "since": _date(d, mo, y) or ""})
    # the managers table (layouts B, C): "Mr. Trideep Bhattacharya 25 years 01-Oct-21"
    for nm, d, mo, y in re.findall(r"(?:Mr|Ms|Mrs|Dr)\.\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+\d+\s+years\s+(\d{1,2})-([A-Za-z]{3})-(\d{2})\b", plain):
        name = " ".join(nm.split())
        if name not in seen:
            seen.add(name)
            managers.append({"name": name, "since": _date(d, mo, "20" + y) or ""})
    if not managers:   # "• Mr. A • Mr. B ... Managing Since Oct 01, 2021 / Oct 14, 2024"
        mm = re.search(r"Name of Fund Managers\s+(.+?)\s+Total\s+Experience.+?Managing\s+Since\s+((?:[A-Za-z]{3}\s+\d{1,2},\s*\d{4}\s*/?\s*)+)", plain)
        if mm:
            names = [n.strip() for n in re.findall(r"(?:Mr|Ms|Mrs|Dr)\.\s*([A-Z][A-Za-z ]+?)(?=\s*•|\s*$)", mm.group(1))]
            dates = re.findall(r"([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})", mm.group(2))
            dates += [None] * len(names)
            managers = [{"name": n, "since": (_date(d[1], d[0], d[2]) or "") if d else ""} for n, d in zip(names, dates)]

    top10 = printed_top10 if printed_top10 is not None else (round(sum(h["pct"] for h in holdings), 2) if len(holdings) == 10 else None)
    fund = {
        "scheme": scheme, "plan": "Direct", "amfi_code": amfi_code, "category": category,
        "benchmark": bm.group(1).strip() if bm else "",
        "aum_cr": aum, "ter_pct": ter if ter is not None else ber,
        "std_dev": grab(r"Standard\s+Deviation\s*\(%\)\s*(\d+\.\d+)", r"(?:Standard|Std\.?)\s*deviation[\d,]*\s*:?\s*(\d+\.\d+)%?"),
        "beta": grab(r"\bBeta\d?\s*:?\s+(\d+\.\d+)", r"\bBeta\d?\s*:\s*(\d+\.\d+)"),
        "sharpe": grab(r"Sharpe\s+Ratio[\d,*]*\s*:?\s*(-?\d+\.\d+)"), "alpha": None, "treynor": None,
        "turnover_pct": round(times * 100, 2) if times is not None else None,
        "top10_pct": top10, "cash_pct": None, "cap_mix": cap,
        "returns": {"1y": r1[0], "3y": r3[0], "5y": r5[0]}, "benchmark_returns": {"1y": r1[1], "3y": r3[1], "5y": r5[1]},
        "managers": managers, "holdings": holdings,
        "notes": (f"Parsed from the Edelweiss scheme pages {first}-{last} (fixed parser). "
                  + ("Expense ratio is the Direct plan's total TER as printed. " if ter is not None else
                     "Expense ratio is the Direct plan's base expense ratio (BER): this layout prints no total TER. ")
                  + f"Equity turnover printed as {times} times. "
                  + ("Only the top 10 holdings are printed (no ISIN / share counts). " if holdings else
                     "Holdings not read from this layout (top-10 share as printed); the full portfolio is in the monthly disclosure. ")
                  + ("" if r3[0] is not None else "Direct-plan returns are not on the scheme page in this layout.")),
    }
    report = {"pages": f"{first}-{last}", "method": loc["method"], "as_on": as_on, "aum_cr": aum, "ter_direct": fund["ter_pct"],
              "ter_kind": "TER" if ter is not None else "BER",
              "std_dev": fund["std_dev"], "beta": fund["beta"], "sharpe": fund["sharpe"], "turnover_pct": fund["turnover_pct"],
              "cap_mix": cap, "returns": fund["returns"], "benchmark_returns": fund["benchmark_returns"],
              "managers": managers, "top10": len(holdings), "top10_pct": fund["top10_pct"]}
    return fund, as_on, report


def parse_morningstar(pdf):
    """A Morningstar fund report (the 2-page "morningstarreport<timestamp>.pdf"): the figures used to cross-check the
    AMC data. Its portfolio (allocation, holdings, net assets) is as of the "Portfolio dd/mm/yyyy" date; trailing
    returns and the 3-year risk measures are Morningstar's own, to about the report date, against its benchmark."""
    flat = re.sub(r"\s+", " ", mx.text(pdf, "1-2", max_chars=10 ** 6, plain=True))

    def g(pattern, cast=_num):
        m = re.search(pattern, flat, re.I)
        return cast(m.group(1)) if m else None
    rep = re.search(r"Report as of (\d{1,2}) ([A-Za-z]+) (\d{4})", flat)
    port = re.search(r"Portfolio (\d{2})/(\d{2})/(\d{4})", flat)
    name = re.search(r"Report as of \d{1,2} [A-Za-z]+ \d{4} (.+?) Morningstar", flat)
    trailing = {}
    for key, label in (("3m", "3 Months"), ("6m", "6 Months"), ("1y", "1 Year"), ("3y", "3 Years Annualised"), ("5y", "5 Years Annualised")):
        m = re.search(re.escape(label) + r"\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)", flat)
        if m:
            trailing[key] = {"fund": float(m.group(1)), "benchmark": float(m.group(2)), "category": float(m.group(3))}
    top = []
    m = re.search(r"Holding Name Sector %(.+?)Assets in Top 10 Holdings", flat)
    if m:
        for nm, pct in re.findall(r"([A-Z][A-Za-z0-9&.,'()\- ]+?)\s+[a-z]\s+(\d+\.\d+)", m.group(1)):
            top.append({"name": nm.strip(), "pct": float(pct)})
    lay = re.sub(r"\s+", " ", mx.text(pdf, "1-2", max_chars=10 ** 6))   # layout order keeps "(mil) 1,450,704.98 INR (30/09/2026)"
    m = re.search(r"Total Net Assets \(mil\)\s+([\d,]+\.\d+)\s*INR\s*\(?(\d{2})?/?(\d{2})?/?(\d{4})?", lay)
    tna = _num(m.group(1)) if m else None
    tna_date = m if m and m.group(4) else None
    return {
        "fund": name.group(1).strip() if name else "",
        "report_date": f"{rep.group(3)}-{MONTHS[rep.group(2).lower()] if rep.group(2).lower() in MONTHS else _month3(rep.group(2)):02d}-{int(rep.group(1)):02d}" if rep else None,
        "portfolio_date": f"{port.group(3)}-{port.group(2)}-{port.group(1)}" if port else None,
        "isin": g(r"\bISIN\s+([A-Z]{2}[A-Z0-9]{9}\d)", str),
        "risk": {"alpha": g(r"3Y Alpha\s+(-?\d+\.\d+)"), "beta": g(r"3Y Beta\s+(-?\d+\.\d+)"),
                 "sharpe": g(r"3Y Sharpe Ratio\s+(-?\d+\.\d+)"), "std_dev": g(r"3Y Std Dev\s+(-?\d+\.\d+)"),
                 "r_squared": g(r"3Y R-Squared\s+(-?\d+\.\d+)"), "info_ratio": g(r"3Y Info Ratio\s+(-?\d+\.\d+)"),
                 "tracking_error": g(r"3Y Tracking Error\s+(-?\d+\.\d+)")},
        "trailing": trailing,
        "allocation": {"stocks": g(r"Stocks\s+(-?\d+\.\d+)"), "bonds": g(r"Bonds\s+(-?\d+\.\d+)"),
                       "cash": g(r"Cash\s+(-?\d+\.\d+)"), "other": g(r"Other\s+(-?\d+\.\d+)")},
        "top10": top, "top10_pct": g(r"Assets in Top 10 Holdings %\s+(\d+\.\d+)"),
        "equity_holdings": g(r"Total Number of Equity Holdings\s+(\d+)", int),
        "bond_holdings": g(r"Total Number of Bond Holdings\s+(\d+)", int),
        "expense_ratio": g(r"Expense Ratio\s+(\d+\.\d+)%"),
        "net_assets_cr": round(tna / 10, 2) if tna is not None else None,   # INR million -> crore
        "net_assets_date": f"{tna_date.group(4)}-{tna_date.group(3)}-{tna_date.group(2)}" if tna_date else None,
        "manager": g(r"Manager Name\s+(.+?)\s+(?:ISIN|Manager Start)", str),
        "manager_start": g(r"Manager Start Date\s+(\d{2}/\d{2}/\d{4})", str),
        "rating_stars": len(re.search(r"Morningstar Rating™ .*? (Q{1,5})\b", flat).group(1)) if re.search(r"Morningstar Rating™ .*? (Q{1,5})\b", flat) else None,
    }


def _month3(name):
    return next((n for m, n in MONTHS.items() if m.startswith(name.lower()[:3])), 0)


PARSERS = {"axis": parse_axis, "edelweiss": parse_edelweiss}
