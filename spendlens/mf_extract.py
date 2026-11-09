"""Read-only helper the mf-factsheet-analyst agent uses on the factsheet folder. It never writes to the database.

    python spendlens/mf_extract.py inventory fund_fact_sheet        # files, their month, which are extracted / changed
    python spendlens/mf_extract.py find fund_fact_sheet/ppfas-mf-factsheet-for-May-2026.pdf "Flexi Cap"   # matching pages / sheets
    python spendlens/mf_extract.py text fund_fact_sheet/ppfas-mf-factsheet-for-May-2026.pdf --pages 5-6  # page text / sheet rows
    python spendlens/mf_extract.py validate fund_fact_sheet/_extracted/2026-05/ppfas-mf-factsheet-for-May-2026.json
    python spendlens/mf_extract.py funds [--email me@x.com]          # MF names / AMFI codes in Holdings to extract

Folder layout: either flat (fund_fact_sheet/<file>, the month read from the file name: "May-2026",
"May_31_2026", "2026-05") or one sub-folder per month (factsheets/2026-05/<file>). Factsheet PDFs and monthly
portfolio disclosures (Excel) side by side. The agent writes <folder>/_extracted/YYYY-MM/<file stem>.json in the
format of mf.py. Excel files are recognised by content: AMCs often name an .xlsx ".xls".
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TYPES = (".pdf", ".xlsx", ".xlsm", ".xls", ".csv")
MONTH_DIR = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


DOC_DATE = re.compile(
    r"\b(?:as\s+(?:on|of|at)|as-on|for the month(?: ended)?|month ended|period ended)\s*:?\s*"
    r"(?:(?P<d>\d{1,2})(?:st|nd|rd|th)?[\s\-/.,]*(?P<m>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?[\s\-/.,]*(?P<y>\d{4}|\d{2})"
    r"|(?P<m2>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(?P<d2>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<y2>\d{4})"
    r"|(?P<nd>\d{1,2})[\-/.](?P<nm>\d{1,2})[\-/.](?P<ny>\d{4}|\d{2}))", re.I)


def doc_month(path, pages=3):
    """YYYY-MM from the "as on <date>" printed on a PDF's first pages, or None. AMCs name files by the month they are
    published (Edelweiss "June 2025" holds May data), so the date inside wins over the file name."""
    try:
        r = _reader(path)
        text = " ".join((r.pages[i].extract_text() or "") for i in range(min(pages, len(r.pages))))
    except Exception:
        return None
    counts = {}
    for m in DOC_DATE.finditer(re.sub(r"\s+", " ", text)):
        if m.group("m"):
            mon, y = MONTHS[m.group("m").lower()[:3]], m.group("y")
        elif m.group("m2"):
            mon, y = MONTHS[m.group("m2").lower()[:3]], m.group("y2")
        else:
            mon, y = int(m.group("nm")), m.group("ny")
            if not 1 <= mon <= 12:
                continue
        y = int(y) + (2000 if len(y) == 2 else 0)
        if 2000 <= y <= 2100:
            k = f"{y}-{mon:02d}"
            counts[k] = counts.get(k, 0) + 1
    return max(counts, key=lambda k: (counts[k], k)) if counts else None


def month_of(path, folder=None):
    """YYYY-MM from a YYYY-MM parent folder, else from the file name; None when it can't be told."""
    path = Path(path)
    if folder is not None and path.parent != Path(folder) and MONTH_DIR.match(path.parent.name):
        return path.parent.name
    name = path.stem.lower()
    m = re.search(r"(20\d{2})[-_ .](0[1-9]|1[0-2])(?!\d)", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-_ .]*(?:\d{1,2}[-_ .,]*)?(20\d{2})", name)
    if m:
        return f"{m.group(2)}-{MONTHS[m.group(1)]:02d}"
    m = re.search(r"(0[1-9]|1[0-2])[-_ .](20\d{2})", name)
    if m:
        return f"{m.group(2)}-{m.group(1)}"
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*[-_ .']+\s*(\d{2})(?!\d)", name)   # "April_25", "Mar-26"
    if m:
        return f"20{m.group(2)}-{MONTHS[m.group(1)]:02d}"
    return None


def extracted_path(folder, month, file_name):
    return Path(folder) / "_extracted" / month / (Path(file_name).stem + ".json")


def inventory(folder):
    """Every factsheet / disclosure under folder (flat or YYYY-MM sub-folders; _extracted is skipped), with its month,
    sha256 and status: new / changed (re-extract) / done / unsupported / month-unknown."""
    folder = Path(folder)
    out = {"folder": str(folder), "months": [], "todo": 0, "skipped": []}
    by_month = {}
    for f in sorted(folder.rglob("*")):
        if not f.is_file() or "_extracted" in f.relative_to(folder).parts or f.name.startswith(("~$", ".")):
            continue
        if f.suffix.lower() not in TYPES:
            out["skipped"].append(f"{f.relative_to(folder)} (not a PDF / Excel / CSV)")
            continue
        name_month = month_of(f, folder)
        inside = doc_month(f) if f.suffix.lower() == ".pdf" else None
        month = inside or name_month
        digest = sha256(f)
        status = "new"
        ex = extracted_path(folder, month, f.name) if month else None
        if month is None:
            status = "month-unknown (read the 'as on' date inside; name the file with the month to make it automatic)"
        elif ex.exists():
            try:
                status = "done" if json.loads(ex.read_text(encoding="utf-8")).get("source_sha256") == digest else "changed"
            except (ValueError, OSError):
                status = "unreadable-json"
        if f.suffix.lower() == ".xls" and excel_kind(f) is None:
            status = "unsupported (not an Excel file despite the .xls name)"
        kind = "factsheet" if f.suffix.lower() == ".pdf" else "portfolio"
        by_month.setdefault(month or "unknown", []).append({
            "file": str(f.relative_to(folder)), "kind_guess": kind, "size_kb": round(f.stat().st_size / 1024), "sha256": digest,
            "status": status, "extracted": str(ex) if ex is not None and ex.exists() else None,
            "name_month": name_month, "doc_month": inside,
            "note": f"named {name_month} but dated {inside} inside" if inside and name_month and inside != name_month else ""})
        out["todo"] += status in ("new", "changed", "unreadable-json") or status.startswith("month-unknown")
    out["months"] = [{"month": m, "files": by_month[m]} for m in sorted(by_month)]
    return out


def excel_kind(path):
    """'xlsx' (a zip, whatever the extension says), 'xls' (the old binary format), or None."""
    with open(path, "rb") as f:
        head = f.read(8)
    if head.startswith(b"PK"):
        return "xlsx"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls"
    return None


def _pdf_pages(path):
    import logging
    import pypdf
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = pypdf.PdfReader(str(path))
    if reader.is_encrypted:
        reader.decrypt("")
    pages = []
    for p in reader.pages:
        t = p.extract_text() or ""
        if len(t.strip()) < 40:   # some factsheets only extract cleanly in layout mode
            try:
                t = p.extract_text(extraction_mode="layout") or t
            except Exception:
                pass
        pages.append(t)
    return pages


def _sheets(path, max_rows=5000):
    import io
    import warnings
    import openpyxl
    with warnings.catch_warnings():   # AMC files carry logos openpyxl can't draw; irrelevant here
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(io.BytesIO(Path(path).read_bytes()), data_only=True)
    out = []
    for ws in wb.worksheets:
        rows = []
        for r in ws.iter_rows(values_only=True):
            cells = ["" if c is None else str(c).strip() for c in r]
            if any(cells):
                rows.append("\t".join(cells).rstrip("\t"))
            if len(rows) >= max_rows:
                rows.append("… (truncated)")
                break
        out.append((ws.title, rows))
    return out


def _xls_sheets(path, max_rows=5000):
    """Old binary .xls through xlrd, in the same shape as _sheets."""
    import xlrd
    book = xlrd.open_workbook(str(path), on_demand=True)
    out = []
    for sh in book.sheets():
        rows = []
        for i in range(sh.nrows):
            cells = []
            for c in sh.row(i):
                v = c.value
                if c.ctype == xlrd.XL_CELL_NUMBER and float(v).is_integer():
                    v = int(v)
                cells.append("" if v in (None, "") else str(v).strip())
            if any(cells):
                rows.append("\t".join(cells).rstrip("\t"))
            if len(rows) >= max_rows:
                rows.append("… (truncated)")
                break
        out.append((sh.name, rows))
    return out


def units(path):
    """[(label, text)]: PDF pages or Excel sheets."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        return [(f"page {i + 1}", t) for i, t in enumerate(_pdf_pages(path))]
    if ext in (".xlsx", ".xlsm") or (ext == ".xls" and excel_kind(path) == "xlsx"):
        return [(f"sheet {name}", "\n".join(rows)) for name, rows in _sheets(path)]
    if ext == ".xls" and excel_kind(path) == "xls":
        return [(f"sheet {name}", "\n".join(rows)) for name, rows in _xls_sheets(path)]
    if ext == ".csv":
        return [("csv", path.read_text(encoding="utf-8-sig", errors="replace"))]
    raise SystemExit(f"{path.name}: not a readable PDF / Excel / CSV file")


TOC_LINE = re.compile(r"^(?P<name>[A-Za-z][^\n]*?)\s*(?:[.…·_]{3,}|\s{2,})\s*(?P<a>\d{1,3})(?:\s*[-–]\s*(?P<b>\d{1,3}))?\s*$")
TOC_RANGE = re.compile(r"^(?P<name>[A-Za-z][^\n]*?[A-Za-z’'s)])\s+(?P<a>\d{1,3})\s*[-–]\s*(?P<b>\d{1,3})\s*$")
GENERIC_BOOKMARK = re.compile(r"^\s*(slide|page|untitled|bookmark)\s*\d*\s*$", re.I)


def _reader(path):
    import logging
    import pypdf
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    r = pypdf.PdfReader(str(path))
    if r.is_encrypted:
        r.decrypt("")
    return r


def _head(reader, i, lines=4, band=0.82):
    """Where a scheme's title sits on page i (0-based): the text printed in the top band of the page (by position,
    not by the order the PDF stores it: Axis puts the title 130 lines into the stream), plus the first stream lines."""
    page = reader.pages[i]
    try:
        y0, h = float(page.mediabox.bottom), float(page.mediabox.height)
    except Exception:
        y0, h = 0.0, 0.0
    top = []

    def visit(text, cm, tm, _fd, _fs):
        if text.strip() and h:
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]   # text position on the page
            if y - y0 >= band * h:
                top.append(text.strip())
    t = page.extract_text(visitor_text=visit) or ""
    first = [x.strip() for x in t.splitlines() if x.strip()][:lines]
    return re.sub(r"\s+", " ", " ".join(top[:40] + first))


def _ranges(starts, total):
    """[(title, start, end)] from sorted [(start, title, explicit_end)]: a section runs until the next one starts."""
    out = []
    for k, (s, title, end) in enumerate(starts):
        nxt = next((s2 for s2, _, _ in starts[k + 1:] if s2 > s), total + 1)
        out.append((title, s, end or nxt - 1))
    return out


def locate(path, pattern):
    """Find the page range of a scheme in a factsheet PDF while reading as little as possible:
    1. bookmarks, when they carry real titles (no page text read);
    2. the index / table of contents on the first pages, each range confirmed by the target page's top lines
       (which also finds any offset between printed and PDF page numbers);
    3. a scan of each page's top lines (the scheme title), grouping consecutive pages.
    Returns {method, ranges: [{from, to, title, verified}], pages_in_file, pages_read}. Pages are 1-based."""
    rx = re.compile(pattern, re.I)
    r = _reader(path)
    total, read = len(r.pages), set()

    def head(i):
        read.add(i)
        return _head(r, i)

    # 1. bookmarks
    items = []

    def walk(o):
        for x in o:
            if isinstance(x, list):
                walk(x)
            else:
                try:
                    items.append((r.get_destination_page_number(x) + 1, (x.title or "").strip()))
                except Exception:
                    pass
    try:
        walk(r.outline)
    except Exception:
        items = []
    real = [it for it in items if it[1] and not GENERIC_BOOKMARK.match(it[1])]
    if items and len(real) >= 0.6 * len(items):
        starts = sorted({(p, t, None) for p, t in real})
        hits = [{"from": a, "to": b, "title": t, "verified": True} for t, a, b in _ranges(starts, total) if rx.search(t)]
        if hits:
            return {"method": "bookmarks", "ranges": hits, "pages_in_file": total, "pages_read": 0}

    # 2. index pages
    entries = []
    for i in range(min(8, total)):
        read.add(i)
        for line in (r.pages[i].extract_text() or "").splitlines():
            line = line.strip()
            m = TOC_LINE.match(line) or TOC_RANGE.match(line)
            if m and int(m.group("a")) <= total + 10:
                entries.append((int(m.group("a")), re.sub(r"[.…·_\s]+$", "", m.group("name")).strip(),
                                int(m.group("b")) if m.group("b") else None))
    if len(entries) >= 5:
        hits = []
        for title, a, b in _ranges(sorted(set(entries)), total):
            if not rx.search(title):
                continue
            off = next((o for o in (0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5) if 0 <= a - 1 + o < total and rx.search(head(a - 1 + o))), None)
            o = off or 0
            hits.append({"from": a + o, "to": min(b + o, total), "title": title, "verified": off is not None})
        if any(h["verified"] for h in hits):
            return {"method": "index", "ranges": [h for h in hits if h["verified"]], "pages_in_file": total, "pages_read": len(read)}

    # 3. page headers
    match = [i for i in range(total) if rx.search(head(i))]
    groups = []
    for i in match:
        if groups and i == groups[-1][1] + 1:
            groups[-1][1] = i
        else:
            groups.append([i, i])
    groups.sort(key=lambda g: (-(g[1] - g[0]), g[0]))   # the scheme's own pages first; a lone later page is usually a summary
    return {"method": "headers", "ranges": [{"from": a + 1, "to": b + 1, "title": _head(r, a, 2)[:120], "verified": True} for a, b in groups],
            "pages_in_file": total, "pages_read": len(read)}


def _page_window(pages):
    if not pages:
        return 1, 10 ** 6
    a, _, b = pages.partition("-")
    return int(a), int(b or a)


def find(path, pattern, pages=None):
    """Pages / sheets mentioning pattern. With pages ("138-141") a PDF is searched only there: use locate first to find
    a scheme's pages, and this to search a named section (e.g. the expense-ratio table) without reading the rest."""
    rx = re.compile(pattern, re.I)
    hits = []
    lo, hi = _page_window(pages)
    if Path(path).suffix.lower() == ".pdf":
        r = _reader(path)
        found = [(f"page {i + 1}", r.pages[i].extract_text() or "") for i in range(max(lo, 1) - 1, min(hi, len(r.pages)))]
    else:
        found = [u for i, u in enumerate(units(path), 1) if lo <= i <= hi]
    for label, text in found:
        n = len(rx.findall(text))
        if n:
            first = rx.search(text)
            s = max(0, first.start() - 80)
            hits.append({"where": label, "matches": n, "context": re.sub(r"\s+", " ", text[s:first.end() + 120])})
    return hits


def _pdf_layout(path, lo, hi):
    """Pages lo..hi (1-based) in layout mode: text kept where it sits on the page, so a label stays on the line of its
    value and two-column blocks read side by side. Far easier to read factsheets this way than plain extraction."""
    import logging
    import pypdf
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = pypdf.PdfReader(str(path))
    if reader.is_encrypted:
        reader.decrypt("")
    out = []
    for i in range(max(lo, 1), min(hi, len(reader.pages)) + 1):
        try:
            t = reader.pages[i - 1].extract_text(extraction_mode="layout") or ""
        except Exception:
            t = reader.pages[i - 1].extract_text() or ""
        out.append((f"page {i}", "\n".join(line.rstrip() for line in t.splitlines() if line.strip())))
    return out


def text(path, pages=None, max_chars=60000, plain=False):
    lo, hi = 1, 10 ** 6
    if pages:
        a, _, b = pages.partition("-")
        lo, hi = int(a), int(b or a)
    if Path(path).suffix.lower() == ".pdf" and not plain:
        us = _pdf_layout(path, lo, hi)
    else:
        us = [u for i, u in enumerate(units(path), 1) if lo <= i <= hi]
    out = "\n\n".join(f"=== {label} ===\n{t}" for label, t in us)
    return out if len(out) <= max_chars else out[:max_chars] + f"\n… (truncated at {max_chars} characters; use --pages)"


def funds(email=None):
    """One user's MF holdings (read-only; the first admin unless --email), so the agent extracts only those schemes.
    Several folios of one scheme come out once."""
    import envlocal
    envlocal.load()
    import mf
    from db.engine import SessionLocal
    from db.models import Holding, User
    with SessionLocal() as s:
        q = s.query(User).filter(User.email == email.strip().lower()) if email else s.query(User).filter(User.role == "admin").order_by(User.id)
        user = q.first()
        if user is None:
            raise SystemExit(f"No user {email}" if email else "No admin user")
        s.info["user_id"] = user.id
        rows, seen = [], set()
        for h in s.query(Holding).filter(Holding.asset_type == "MF").order_by(Holding.name):
            k = h.scheme_code or mf.scheme_key(h.name)   # the AMFI code first: the surest sign of one scheme
            if h.visible != 0 and k not in seen:
                seen.add(k)
                rows.append({"name": h.name, "amfi_code": h.scheme_code or "", "group": h.grp or ""})
        return rows


# ---------------------------------------------------------------- monthly portfolio disclosure (Excel), no AI needed

ISIN_RX = re.compile(r"^(IN[A-Z0-9]{10}|[A-Z]{2}[A-Z0-9]{9}\d)$")
RATING_RX = re.compile(r"\b(A1\+?|A2\+?|AAA|AA[+-]?|A[+-]?|BBB[+-]?|SOV|SOVEREIGN)\b", re.I)
CASH_NAME = re.compile(r"treps|tri-?party|reverse repo|\brepo\b|net receivable|net current|net payable|cash|margin|clearing", re.I)
CASH_CODE = re.compile(r"^(TRP|REP|TREP|CBLO)", re.I)
AS_ON = re.compile(r"(?:as on|as at|for the month ended|period ended)?\s*"
                   r"(?P<d>\d{1,2})?(?:st|nd|rd|th)?\s*[-/ ]?\s*(?P<m>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*[-/ ,]*"
                   r"(?P<d2>\d{1,2})?(?:st|nd|rd|th)?,?\s*[-/ ]?\s*(?P<y>20\d{2})", re.I)


def _cells(row):
    return row.split("\t")


def _num(v):
    v = (v or "").strip().replace(",", "")
    if not v or v.upper() in ("NIL", "-", "NA", "N.A."):
        return None
    if v.startswith("$"):        # "$0.00%": printed as less than 0.01%
        return 0.0
    v = v.rstrip("%").strip()
    try:
        return float(v)
    except ValueError:
        return None


def _sheet_map(path):
    if Path(path).suffix.lower() == ".xls" and excel_kind(path) == "xls":
        return _xls_sheets(path, max_rows=20000)
    return _sheets(path, max_rows=20000)


def _title(rows, n=4):
    return " ".join(c for r in rows[:n] for c in _cells(r) if c.strip())


def _header(rows):
    """(row index, {name, isin, qty, pct, ind}) of the table header: the row naming ISIN and a % of NAV column."""
    for i, r in enumerate(rows[:40]):
        cells = [re.sub(r"\s+", " ", c).strip().lower() for c in _cells(r)]   # headings wrap: "% to Net\n Assets"
        if not any("isin" == c or c.startswith("isin") for c in cells):
            continue
        col = {}
        for j, c in enumerate(cells):
            if c.startswith("isin"):
                col["isin"] = j
            elif "quantity" in c or c in ("qty", "no. of shares", "units"):
                col.setdefault("qty", j)
            elif "%" in c and ("nav" in c or "net asset" in c or "aum" in c):
                col.setdefault("pct", j)
            elif ("name" in c and "instrument" in c) or c in ("name", "security", "name of the security", "company", "issuer"):
                col.setdefault("name", j)
            elif "industry" in c or "rating" in c or "sector" in c:
                col.setdefault("ind", j)
        if "pct" in col:
            col.setdefault("name", max(0, col["isin"] - 1))
            return i, col
    return None, None


def as_on_month(rows):
    m = AS_ON.search(_title(rows, 6))
    if not m:
        return None, None
    month = MONTHS[m.group("m").lower()[:3]]
    day = m.group("d") or m.group("d2")
    return f"{m.group('y')}-{month:02d}", (f"{m.group('y')}-{month:02d}-{int(day):02d}" if day else None)


def _scheme_name(title):
    t = re.split(r"\(|monthly portfolio|portfolio statement|portfolio as on", title, flags=re.I)[0]
    return re.sub(r"\s+", " ", t).strip(" -:")


def parse_disclosure(path, funds):
    """Holdings of each held fund from a monthly portfolio disclosure, by column headings (any AMC using the SEBI
    format). funds: [{name, amfi_code}]. Returns (payload, report). Raises SystemExit when a held fund's sheet is
    found but its table can't be read."""
    import mf
    sheets = _sheet_map(path)
    index = {}
    for name, rows in sheets:
        if name.strip().lower() in ("index", "contents", "scheme index"):
            for r in rows:
                cells = [c.strip() for c in _cells(r) if c.strip()]
                for k in range(len(cells) - 1):
                    if re.fullmatch(r"[A-Z0-9_]{2,12}", cells[k]):
                        index[cells[k]] = cells[k + 1]
    want = []
    for f in funds:
        key = mf.scheme_key(f["name"]).split("|")[0]
        if key not in {w[0] for w in want}:
            want.append((key, f))
    out_funds, report, months = [], [], set()
    for key, f in want:
        best, score = None, 0.0
        tok = set(key.split())
        for name, rows in sheets:
            if name.strip().lower() in ("index", "contents", "scheme index") or _header(rows)[0] is None:
                continue   # only sheets that hold a portfolio table (an index lists every scheme's name)
            title = index.get(name, "") + " " + _title(rows)
            st = set(mf.scheme_key(_scheme_name(title) or title).split("|")[0].split())
            if not st or not tok:
                continue
            sc = len(tok & st) / len(tok)
            if sc > score:
                best, score = (name, rows, title), sc
        if not best or score < 0.85:
            report.append({"fund": f["name"], "found": False})
            continue
        name, rows, title = best
        h, col = _header(rows)
        if h is None:
            raise SystemExit(f"{Path(path).name}: sheet {name} ({f['name']}): no header row with ISIN and % of NAV")
        month, as_on = as_on_month(rows)
        if month:
            months.add(month)
        lines = []
        for r in rows[h + 1:]:
            c = _cells(r) + [""] * 20
            nm = c[col["name"]].strip()
            first = " ".join(x.strip() for x in c[:3] if x.strip())
            if re.search(r"grand total", first, re.I):
                break
            isin = c[col["isin"]].strip().upper()
            p = _num(c[col["pct"]])
            if p is None:
                continue
            ind = c[col["ind"]].strip() if "ind" in col else ""
            ind = re.sub(r"\s*#+$", "", ind)
            if ISIN_RX.match(isin):
                rating = ind if RATING_RX.search(ind) and not re.search(r"[a-z]{4,}", ind.replace("Sovereign", "")) else ""
                lines.append({"name": re.sub(r"\s*#+$", "", nm), "isin": isin, "pct": p, "qty": _num(c[col["qty"]]) if "qty" in col else None,
                              "sector": "" if rating else ind, "rating": rating})
            elif CASH_CODE.match(c[0].strip()) or CASH_CODE.match(nm) or CASH_NAME.search(nm):
                if re.search(r"total", first, re.I):
                    continue
                label = "TREPS" if re.match(r"^(TRP|TREP)", c[0].strip() or nm, re.I) else "Reverse Repo" if re.match(r"^REP", c[0].strip() or nm, re.I) else ""
                lines.append({"name": f"{label} ({nm})" if label and not CASH_NAME.search(nm) else nm, "isin": "", "pct": p, "qty": None,
                              "sector": "", "rating": ""})
        isin_total = sum(x["pct"] for x in lines if x["isin"])
        scale = 100.0 if isin_total <= 1.2 else 1.0     # % printed as a fraction (0.022 = 2.2%), judged on the ISIN lines
        for x in lines:
            x["pct"] = round(x["pct"] * scale, 4)
        total = round(sum(x["pct"] for x in lines), 2)
        fixed = None
        net = next((x for x in lines if re.search(r"net receivable|net current|net payable", x["name"], re.I)), None)
        if abs(total - 100) > 2 and net is not None:
            # the balancing line printed in another unit (seen: 0.676 where -0.02 was due): recompute it, keep a note
            printed = net["pct"]
            net["pct"] = round(100 - (total - printed), 4)
            fixed = f"{net['name']} printed as {printed / scale:g}; recomputed as the balancing figure {net['pct']:g}%"
            total = round(sum(x["pct"] for x in lines), 2)
        scheme = _scheme_name(_title(rows, 2)) or f["name"]
        out_funds.append({"scheme": re.sub(r"\s*\(folio[^)]*\)", "", scheme, flags=re.I), "plan": "Direct", "amfi_code": f.get("amfi_code", ""),
                          "holdings": lines,
                          "notes": f"From disclosure sheet {name}" + (" (% to NAV printed as a fraction, ×100)" if scale == 100 else "") + (f"; {fixed}" if fixed else "")
                                   + (f"; as on {as_on}" if as_on else "") + ". Holdings are the whole portfolio (plan-independent)."})
        report.append({"fund": f["name"], "found": True, "sheet": name, "lines": len(lines), "total_pct": total, "fixed": fixed,
                       "with_qty": sum(1 for x in lines if x["qty"] is not None), "as_on": as_on})
    month = months.pop() if len(months) == 1 else month_of(path)
    dates = {x.get("as_on") for x in report if x.get("as_on")}
    payload = {"month": month, "as_on": dates.pop() if len(dates) == 1 else "", "source": Path(path).name,
               "source_sha256": sha256(path), "kind": "portfolio",
               "amc": "", "funds": out_funds}
    return payload, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inventory").add_argument("folder")
    lo = sub.add_parser("locate", help="page range of a scheme in a factsheet PDF (bookmarks, then the index, then page titles)")
    lo.add_argument("file")
    lo.add_argument("pattern")
    f = sub.add_parser("find")
    f.add_argument("file")
    f.add_argument("pattern")
    f.add_argument("--pages", help="only these PDF pages / sheets, e.g. 138-141")
    t = sub.add_parser("text")
    t.add_argument("file")
    t.add_argument("--pages", help="e.g. 41-42 (PDF pages or Excel sheets, 1-based)")
    t.add_argument("--max-chars", type=int, default=60000)
    t.add_argument("--plain", action="store_true", help="PDF: plain extraction instead of layout mode")
    sub.add_parser("validate").add_argument("json_file")
    fs = sub.add_parser("factsheet", help="parse a factsheet PDF with a fixed AMC parser (mf_parsers.PARSERS), no AI needed")
    fs.add_argument("file")
    fs.add_argument("--amc", required=True, help="parser name, e.g. axis")
    fs.add_argument("--scheme", required=True, help="the scheme name as the factsheet prints it")
    fs.add_argument("--amfi", default="")
    fs.add_argument("--category", default="")
    fs.add_argument("--amc-name", default="", help="AMC name for the JSON, e.g. 'Axis Mutual Fund'")
    fs.add_argument("--write", action="store_true")
    fs.add_argument("--folder", default="fund_fact_sheet")
    d = sub.add_parser("disclosure", help="parse a monthly portfolio disclosure (Excel) for the held funds, no AI needed")
    d.add_argument("file")
    d.add_argument("--funds", required=True, help="JSON list of {name, amfi_code} (the output of `funds`)")
    d.add_argument("--amc", default="", help="AMC name for the JSON, e.g. 'PPFAS Mutual Fund'")
    d.add_argument("--write", action="store_true", help="write <folder>/_extracted/<month>/<stem>.json")
    d.add_argument("--folder", default="fund_fact_sheet")
    sub.add_parser("funds").add_argument("--email")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if a.cmd == "inventory":
        print(json.dumps(inventory(a.folder), indent=1))
    elif a.cmd == "locate":
        print(json.dumps(locate(a.file, a.pattern), indent=1, ensure_ascii=False))
    elif a.cmd == "find":
        print(json.dumps(find(a.file, a.pattern, a.pages), indent=1, ensure_ascii=False))
    elif a.cmd == "text":
        print(text(a.file, a.pages, a.max_chars, a.plain))
    elif a.cmd == "validate":
        import mf
        payload = json.loads(Path(a.json_file).read_text(encoding="utf-8"))
        errors, warnings = mf.validate(payload)
        print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings}, indent=1, ensure_ascii=False))
        sys.exit(1 if errors else 0)
    elif a.cmd == "factsheet":
        import mf
        import mf_parsers
        if a.amc not in mf_parsers.PARSERS:
            raise SystemExit(f"no fixed parser for {a.amc}; known: {', '.join(mf_parsers.PARSERS)} (use the agent)")
        fund, as_on, report = mf_parsers.PARSERS[a.amc](a.file, a.scheme, a.amfi, a.category)
        month = as_on[:7] if as_on else month_of(a.file)
        payload = {"month": month, "as_on": as_on or "", "source": Path(a.file).name, "source_sha256": sha256(a.file),
                   "kind": "factsheet", "amc": a.amc_name, "funds": [fund]}
        errors, warnings = mf.validate(payload)
        out = None
        if a.write and not errors and month:
            out = extracted_path(a.folder, month, payload["source"])
            if out.exists():   # another fund of the same AMC file already extracted: keep it, replace this one
                prev = json.loads(out.read_text(encoding="utf-8"))
                prev["funds"] = [f for f in prev.get("funds", []) if mf.scheme_key(f["scheme"], f.get("plan", "")) != mf.scheme_key(fund["scheme"], "Direct")] + [fund]
                prev.update({k: payload[k] for k in ("month", "as_on", "source", "source_sha256", "kind")})
                payload = prev
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"month": month, "report": report, "errors": errors, "warnings": warnings,
                          "written": str(out) if out else None}, indent=1, ensure_ascii=False))
        sys.exit(1 if errors else 0)
    elif a.cmd == "disclosure":
        import mf
        payload, report = parse_disclosure(a.file, json.loads(Path(a.funds).read_text(encoding="utf-8")))
        payload["amc"] = a.amc
        errors, warnings = mf.validate(payload) if payload["funds"] else (["no held fund found in this file"], [])
        out = None
        if a.write and not errors and payload["month"]:
            out = extracted_path(a.folder, payload["month"], payload["source"])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"month": payload["month"], "report": report, "errors": errors, "warnings": warnings,
                          "written": str(out) if out else None}, indent=1, ensure_ascii=False))
        sys.exit(1 if errors else 0)
    elif a.cmd == "funds":
        print(json.dumps(funds(a.email), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
