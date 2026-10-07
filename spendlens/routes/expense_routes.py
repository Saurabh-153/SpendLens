import calendar
import io
import json
from datetime import date
import cards
from forecast import build_forecast
from accrual import auto_value, is_auto
from sip import apply_due_sips, set_sip
import portfolio as pf
import prices as px
import ledger as led
from subcategories import (normalize, sub_allowed, subcategories_for_month, subcategory_status)
from database import (get_db, budget_for_month, categories_for_month, category_allowed_in_month,
                      current_month, next_month, prev_month)
from pydantic import BaseModel
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from ._common import get_db_dep

router = APIRouter(prefix="/spendlens/api", tags=["expense"])


def parse_month(month):
    """Return (month, year, mon) for a YYYY-MM string (default: current month); 400 if invalid."""
    month = month or date.today().strftime("%Y-%m")
    try:
        year, mon = map(int, month.split("-"))
        date(year, mon, 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    return month, year, mon


class CategoryCreate(BaseModel):
    name: str
    icon: str = "📦"
    color: str = "#64748b"
    hint: str = ""
    start_month: str | None = None
    target_pct: float = 0


class CategoryUpdate(BaseModel):
    name: str
    icon: str = "📦"
    color: str = "#64748b"
    hint: str = ""


class ArchiveRequest(BaseModel):
    from_month: str | None = None


class TargetSet(BaseModel):
    from_month: str
    target_pct: float


class BudgetSet(BaseModel):
    from_month: str
    income: float
    savings_amount: float


class ReorderRequest(BaseModel):
    ids: list[int]


class ExpenseCreate(BaseModel):
    category_id: int
    date: str
    amount: float
    note: str = ""
    cashback: float = 0
    user_id: int = 1
    subcategory_id: int | None = None


class ExpenseUpdate(BaseModel):
    category_id: int
    date: str
    amount: float
    note: str = ""
    cashback: float = 0
    subcategory_id: int | None = None


class EntryIn(BaseModel):
    id: int | None = None
    subcategory_id: int | None = None
    amount: float
    note: str = ""


class CellEntries(BaseModel):
    category_id: int
    date: str
    entries: list[EntryIn]


class SubCreate(BaseModel):
    category_id: int
    name: str
    start_month: str | None = None


class SubUpdate(BaseModel):
    name: str


class ReviewMap(BaseModel):
    category_id: int
    note: str = ""
    subcategory_id: int


class RangeSet(BaseModel):
    category_id: int
    month: str
    start_day: int
    end_day: int
    amount: float
    subcategory_id: int | None = None
    note: str = ""
    mode: str = "replace"  # 'replace' existing entries on those days, or 'add' on top


@router.get("/healthz")
def health():
    return {"status": "ok"}


def category_status(c, today):
    if c["start_month"] > today:
        return "scheduled"
    if c["end_month"] is not None and c["end_month"] < today:
        return "archived"
    return "active"


def ensure_category_open(db, category_id, month):
    """Reject new spend on a category that is not active in that month (keeps history unchanged)."""
    parse_month(month)
    if not category_allowed_in_month(db, category_id, month):
        db.close()
        raise HTTPException(status_code=400, detail="Category is not active in " + month)


def ensure_sub_ok(db, category_id, sub_id, month, keep_sub_id=None):
    if sub_id is not None and not sub_allowed(db, category_id, sub_id, month, keep_sub_id):
        db.close()
        raise HTTPException(status_code=400, detail="Sub-category is not valid for this category and month")


def get_category_or_404(db, cid):
    row = db.execute("SELECT * FROM categories WHERE id=?", (cid,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Category not found")
    return row


def category_view(db, cid):
    today = current_month()
    row = dict(get_category_or_404(db, cid))
    t = db.execute("""SELECT target_pct FROM category_targets WHERE category_id=? AND from_month<=?
                      ORDER BY from_month DESC LIMIT 1""", (cid, today)).fetchone()
    row["target_pct"] = t["target_pct"] if t else 0
    row["status"] = category_status(row, today)
    row["has_data"] = bool(db.execute("SELECT 1 FROM expenses WHERE category_id=? LIMIT 1", (cid,)).fetchone())
    return row


@router.get("/categories")
def get_categories(month: str = Query(None), db=Depends(get_db_dep)):
    """Without `month`: every category with its lifecycle status. With `month`: those shown in that month."""
    if month:
        result = categories_for_month(db, parse_month(month)[0])
    else:
        ids = [r["id"] for r in db.execute("SELECT id FROM categories ORDER BY sort_order, id")]
        result = [category_view(db, i) for i in ids]
    db.close()
    return result


@router.post("/categories", status_code=201)
def create_category(data: CategoryCreate, db=Depends(get_db_dep)):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    start = parse_month(data.start_month)[0]
    if db.execute("SELECT 1 FROM categories WHERE lower(name)=lower(?) AND end_month IS NULL", (name,)).fetchone():
        db.close()
        raise HTTPException(status_code=409, detail="An active category with this name already exists")
    order = db.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM categories").fetchone()[0]
    cur = db.execute("""INSERT INTO categories (name, icon, color, target_pct, hint, visible, sort_order, start_month)
        VALUES (?,?,?,?,?,1,?,?)""", (name, data.icon, data.color, data.target_pct, data.hint, order, start))
    db.execute("INSERT INTO category_targets (category_id, from_month, target_pct) VALUES (?,?,?)",
               (cur.lastrowid, start, data.target_pct))
    db.commit()
    view = category_view(db, cur.lastrowid)
    db.close()
    return view


@router.put("/categories/reorder")
def reorder_categories(data: ReorderRequest, db=Depends(get_db_dep)):
    for i, cid in enumerate(data.ids, start=1):
        db.execute("UPDATE categories SET sort_order=? WHERE id=?", (i, cid))
    db.commit()
    db.close()
    return {"ok": True}


@router.put("/categories/{cid}")
def update_category(cid: int, data: CategoryUpdate, db=Depends(get_db_dep)):
    """Rename / restyle. Label-only: applies to every month, no amounts change."""
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    get_category_or_404(db, cid)
    db.execute("UPDATE categories SET name=?, icon=?, color=?, hint=? WHERE id=?",
               (name, data.icon, data.color, data.hint, cid))
    db.commit()
    view = category_view(db, cid)
    db.close()
    return view


@router.post("/categories/{cid}/archive")
def archive_category(cid: int, data: ArchiveRequest, db=Depends(get_db_dep)):
    """Hide a category from `from_month` onward (default next month); earlier months are unchanged."""
    from_month = parse_month(data.from_month or next_month(current_month()))[0]
    cat = get_category_or_404(db, cid)
    if from_month <= cat["start_month"]:
        db.close()
        raise HTTPException(status_code=400, detail="Archive month must be after the month the category starts")
    db.execute("UPDATE categories SET end_month=? WHERE id=?", (prev_month(from_month), cid))
    later = db.execute("SELECT COUNT(DISTINCT substr(date,1,7)) FROM expenses WHERE category_id=? AND substr(date,1,7)>=?",
                       (cid, from_month)).fetchone()[0]
    db.commit()
    view = category_view(db, cid)
    db.close()
    return {**view, "months_with_data_after": later}


@router.post("/categories/{cid}/restore")
def restore_category(cid: int, db=Depends(get_db_dep)):
    get_category_or_404(db, cid)
    db.execute("UPDATE categories SET end_month=NULL WHERE id=?", (cid,))
    db.commit()
    view = category_view(db, cid)
    db.close()
    return view


@router.get("/categories/{cid}/usage")
def category_usage(cid: int, db=Depends(get_db_dep)):
    """What a category holds, so a delete can be double-checked: its entries, their total and date range, and what else
    would go with it. A category with entries can never be deleted (archive it instead)."""
    try:
        get_category_or_404(db, cid)
        n, total, first, last = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount), 0), MIN(date), MAX(date) FROM expenses WHERE category_id=?", (cid,)).fetchone()
        months = db.execute("SELECT COUNT(DISTINCT substr(date,1,7)) FROM expenses WHERE category_id=?", (cid,)).fetchone()[0]
        subs = db.execute("SELECT COUNT(*) FROM subcategories WHERE category_id=?", (cid,)).fetchone()[0]
        targets = db.execute("SELECT COUNT(*) FROM category_targets WHERE category_id=?", (cid,)).fetchone()[0]
        return {"entries": n, "total": round(total, 2), "first": first, "last": last, "months": months,
                "subcategories": subs, "target_changes": targets, "can_delete": n == 0}
    finally:
        db.close()


@router.delete("/categories/{cid}")
def delete_category(cid: int, db=Depends(get_db_dep)):
    """Hard delete only for categories that never had an expense; otherwise archive."""
    get_category_or_404(db, cid)
    if db.execute("SELECT 1 FROM expenses WHERE category_id=? LIMIT 1", (cid,)).fetchone():
        db.close()
        raise HTTPException(status_code=409, detail="Category has expense history - archive it instead")
    # With no expenses there is nothing to orphan. Its sub-categories and their rules go with it (they would otherwise
    # block the delete, since each refers to the category).
    db.execute("DELETE FROM subcategory_rules WHERE category_id=?", (cid,))
    db.execute("DELETE FROM subcategories WHERE category_id=?", (cid,))
    db.execute("DELETE FROM category_targets WHERE category_id=?", (cid,))
    db.execute("DELETE FROM categories WHERE id=?", (cid,))
    db.commit()
    db.close()
    return {"ok": True}


@router.get("/categories/{cid}/targets")
def category_target_history(cid: int, db=Depends(get_db_dep)):
    get_category_or_404(db, cid)
    rows = db.execute("SELECT from_month, target_pct FROM category_targets WHERE category_id=? ORDER BY from_month",
                      (cid,)).fetchall()
    db.close()
    return [dict(r) for r in rows]


@router.put("/categories/{cid}/target")
def set_category_target(cid: int, data: TargetSet, db=Depends(get_db_dep)):
    """Target % valid from `from_month` onward; earlier months keep their previous target."""
    month = parse_month(data.from_month)[0]
    if not 0 <= data.target_pct <= 100:
        raise HTTPException(status_code=400, detail="Target must be between 0 and 100")
    data.target_pct = round(data.target_pct, 8)   # keep enough precision that a typed rupee amount round-trips exactly
    get_category_or_404(db, cid)
    db.execute("""INSERT INTO category_targets (category_id, from_month, target_pct) VALUES (?,?,?)
                  ON CONFLICT(category_id, from_month) DO UPDATE SET target_pct=excluded.target_pct""",
               (cid, month, data.target_pct))
    db.commit()
    db.close()
    return {"ok": True}


@router.get("/budget")
def budget_history(db=Depends(get_db_dep)):
    rows = db.execute("SELECT from_month, income, savings_amount FROM budget_history ORDER BY from_month").fetchall()
    db.close()
    return [dict(r) for r in rows]


@router.put("/budget")
def set_budget(data: BudgetSet, db=Depends(get_db_dep)):
    """Income / savings % valid from `from_month` onward."""
    month = parse_month(data.from_month)[0]
    if data.income < 0 or not 0 <= data.savings_amount <= data.income:
        raise HTTPException(status_code=400, detail="Savings must be between 0 and the salary")
    db.execute("""INSERT INTO budget_history (from_month, income, savings_amount) VALUES (?,?,?)
                  ON CONFLICT(from_month) DO UPDATE SET income=excluded.income, savings_amount=excluded.savings_amount""",
               (month, round(data.income, 2), round(data.savings_amount, 2)))
    db.commit()
    db.close()
    return {"ok": True}


def sub_view(db, sid):
    today = current_month()
    row = db.execute("SELECT * FROM subcategories WHERE id=?", (sid,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Sub-category not found")
    d = dict(row)
    d["status"] = subcategory_status(d, today)
    d["has_data"] = bool(db.execute("SELECT 1 FROM expenses WHERE subcategory_id=? LIMIT 1", (sid,)).fetchone())
    return d


@router.get("/subcategories")
def get_subcategories(category_id: int = Query(None), month: str = Query(None), db=Depends(get_db_dep)):
    """With `month`: those usable/shown in that month. Without: all, with lifecycle status."""
    if month:
        result = subcategories_for_month(db, parse_month(month)[0], category_id)
    else:
        q = "SELECT id FROM subcategories" + (" WHERE category_id=?" if category_id else "") + " ORDER BY category_id, sort_order, id"
        ids = [r["id"] for r in db.execute(q, ([category_id] if category_id else []))]
        result = [sub_view(db, i) for i in ids]
    db.close()
    return result


@router.post("/subcategories", status_code=201)
def create_subcategory(data: SubCreate, db=Depends(get_db_dep)):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    start = parse_month(data.start_month)[0]
    get_category_or_404(db, data.category_id)
    if db.execute("""SELECT 1 FROM subcategories WHERE category_id=? AND lower(name)=lower(?) AND end_month IS NULL""",
                  (data.category_id, name)).fetchone():
        db.close()
        raise HTTPException(status_code=409, detail="This category already has an active sub-category with that name")
    order = db.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM subcategories WHERE category_id=?", (data.category_id,)).fetchone()[0]
    cur = db.execute("INSERT INTO subcategories (category_id, name, sort_order, start_month) VALUES (?,?,?,?)",
                     (data.category_id, name, order, start))
    db.commit()
    view = sub_view(db, cur.lastrowid)
    db.close()
    return view


@router.put("/subcategories/reorder")
def reorder_subcategories(data: ReorderRequest, db=Depends(get_db_dep)):
    for i, sid in enumerate(data.ids, start=1):
        db.execute("UPDATE subcategories SET sort_order=? WHERE id=?", (i, sid))
    db.commit()
    db.close()
    return {"ok": True}


@router.get("/subcategories/review")
def subcategory_review(db=Depends(get_db_dep)):
    """Entries without a sub-category, grouped by category + note, for the Admin 'Needs review' list."""
    rows = db.execute("""SELECT e.id, e.category_id, c.name AS category, e.note, e.amount
                         FROM expenses e JOIN categories c ON c.id=e.category_id
                         WHERE e.subcategory_id IS NULL AND EXISTS (SELECT 1 FROM subcategories s WHERE s.category_id=e.category_id)
                         ORDER BY c.sort_order""").fetchall()
    db.close()
    groups = {}
    for r in rows:
        key = (r["category_id"], normalize(r["note"]))
        g = groups.setdefault(key, {"category_id": r["category_id"], "category": r["category"], "note": key[1], "count": 0, "total": 0})
        g["count"] += 1
        g["total"] += r["amount"]
    return sorted(groups.values(), key=lambda g: (-g["count"], g["category"]))


@router.post("/subcategories/review/map")
def subcategory_review_map(data: ReviewMap, db=Depends(get_db_dep)):
    """Assign a sub-category to every unmapped entry with this note, and remember the note as a rule."""
    sub = db.execute("SELECT * FROM subcategories WHERE id=?", (data.subcategory_id,)).fetchone()
    if not sub or sub["category_id"] != data.category_id:
        db.close()
        raise HTTPException(status_code=400, detail="Sub-category does not belong to this category")
    note = normalize(data.note)
    ids = [r["id"] for r in db.execute("SELECT id, note FROM expenses WHERE category_id=? AND subcategory_id IS NULL",
                                       (data.category_id,)).fetchall() if normalize(r["note"]) == note]
    for eid in ids:
        db.execute("UPDATE expenses SET subcategory_id=? WHERE id=?", (data.subcategory_id, eid))
    if note and not db.execute("SELECT 1 FROM subcategory_rules WHERE category_id=? AND pattern=? AND match_type='exact'",
                               (data.category_id, note)).fetchone():
        db.execute("INSERT INTO subcategory_rules (category_id, pattern, match_type, subcategory_id) VALUES (?,?, 'exact', ?)",
                   (data.category_id, note, data.subcategory_id))
    db.commit()
    db.close()
    return {"updated": len(ids)}


@router.put("/subcategories/{sid}")
def update_subcategory(sid: int, data: SubUpdate, db=Depends(get_db_dep)):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    sub_view(db, sid)
    db.execute("UPDATE subcategories SET name=? WHERE id=?", (name, sid))
    db.commit()
    view = sub_view(db, sid)
    db.close()
    return view


@router.post("/subcategories/{sid}/archive")
def archive_subcategory(sid: int, data: ArchiveRequest, db=Depends(get_db_dep)):
    from_month = parse_month(data.from_month or next_month(current_month()))[0]
    sub = sub_view(db, sid)
    if from_month <= sub["start_month"]:
        db.close()
        raise HTTPException(status_code=400, detail="Archive month must be after the month the sub-category starts")
    db.execute("UPDATE subcategories SET end_month=? WHERE id=?", (prev_month(from_month), sid))
    later = db.execute("SELECT COUNT(DISTINCT substr(date,1,7)) FROM expenses WHERE subcategory_id=? AND substr(date,1,7)>=?",
                       (sid, from_month)).fetchone()[0]
    db.commit()
    view = sub_view(db, sid)
    db.close()
    return {**view, "months_with_data_after": later}


@router.post("/subcategories/{sid}/restore")
def restore_subcategory(sid: int, db=Depends(get_db_dep)):
    sub_view(db, sid)
    db.execute("UPDATE subcategories SET end_month=NULL WHERE id=?", (sid,))
    db.commit()
    view = sub_view(db, sid)
    db.close()
    return view


@router.delete("/subcategories/{sid}")
def delete_subcategory(sid: int, db=Depends(get_db_dep)):
    sub_view(db, sid)
    if db.execute("SELECT 1 FROM expenses WHERE subcategory_id=? LIMIT 1", (sid,)).fetchone():
        db.close()
        raise HTTPException(status_code=409, detail="Sub-category has expenses - archive it instead")
    db.execute("DELETE FROM subcategory_rules WHERE subcategory_id=?", (sid,))
    db.execute("DELETE FROM subcategories WHERE id=?", (sid,))
    db.commit()
    db.close()
    return {"ok": True}


@router.get("/expenses")
def get_expenses(month: str = Query(None), db=Depends(get_db_dep)):
    if month:
        rows = db.execute("""
            SELECT e.*, c.name as cat_name, c.icon, c.color
            FROM expenses e JOIN categories c ON c.id=e.category_id
            WHERE e.date LIKE ? ORDER BY e.date, e.id""", (f"{month}-%",)).fetchall()
    else:
        rows = db.execute("""
            SELECT e.*, c.name as cat_name, c.icon, c.color
            FROM expenses e JOIN categories c ON c.id=e.category_id
            ORDER BY e.date DESC, e.id DESC LIMIT 200""").fetchall()
    db.close()
    return [dict(r) for r in rows]


@router.get("/expenses/months")
def get_expense_months(db=Depends(get_db_dep)):
    rows = db.execute("SELECT DISTINCT strftime('%Y-%m', date) as m FROM expenses ORDER BY m DESC").fetchall()
    db.close()
    return [r["m"] for r in rows]


@router.get("/expenses/monthly-grid")
def get_monthly_grid(month: str = Query(None), db=Depends(get_db_dep)):
    month, year, mon = parse_month(month)
    days_in_month = calendar.monthrange(year, mon)[1]

    cats = categories_for_month(db, month)
    expenses = db.execute(
        "SELECT * FROM expenses WHERE date LIKE ? ORDER BY date, id",
        (f"{month}-%",)
    ).fetchall()
    budget = budget_for_month(db, month)
    sub_list = subcategories_for_month(db, month)
    db.close()

    income = budget["income"]
    budget_cap = round(budget["budget_cap"])

    exp_map = {}
    for e in expenses:
        d = int(e["date"].split("-")[2])
        key = (e["category_id"], d)
        if key not in exp_map:
            exp_map[key] = {"amount": 0, "cashback": 0, "note": "", "expense_id": e["id"], "entries": []}
        exp_map[key]["amount"] += e["amount"]
        exp_map[key]["cashback"] += e["cashback"]
        if e["note"]:
            existing = exp_map[key]["note"]
            exp_map[key]["note"] = (existing + "; " + e["note"]) if existing else e["note"]
        exp_map[key]["expense_id"] = e["id"]
        exp_map[key]["entries"].append({"id": e["id"], "subcategory_id": e["subcategory_id"], "amount": e["amount"],
                                        "note": e["note"], "cashback": e["cashback"]})

    categories = []
    total_spent = 0
    total_cashback = 0
    days_with_spend = set()

    for cat in cats:
        row_total = 0
        row_cashback = 0
        days = {}
        sub_totals = {}
        for d in range(1, days_in_month + 1):
            key = (cat["id"], d)
            if key in exp_map:
                cell = exp_map[key]
                days[d] = cell
                for en in cell["entries"]:
                    sub_totals[en["subcategory_id"]] = sub_totals.get(en["subcategory_id"], 0) + en["amount"]
                row_total += cell["amount"]
                row_cashback += cell["cashback"]
                days_with_spend.add(d)
        total_cashback += row_cashback

        cat_dict = dict(cat)
        cat_dict["total"] = row_total
        cat_dict["cashback"] = row_cashback
        cat_dict["days"] = days
        cat_dict["subs"] = [{"subcategory_id": k, "total": v} for k, v in sub_totals.items()]
        categories.append(cat_dict)
        total_spent += row_total

    extra_saving = max(0, budget_cap - total_spent)

    return {
        "month": month,
        "days": days_in_month,
        "categories": categories,
        "subcategories": sub_list,
        "total_spent": total_spent,
        "total_cashback": total_cashback,
        "income": income,
        "budget_cap": budget_cap,
        "extra_saving": extra_saving,
        "days_logged": len(days_with_spend),
    }


@router.get("/expenses/{eid}")
def get_expense(eid: int, db=Depends(get_db_dep)):
    row = db.execute("""SELECT e.*, c.name as cat_name, c.icon, c.color
        FROM expenses e JOIN categories c ON c.id=e.category_id WHERE e.id=?""", (eid,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return dict(row)


@router.put("/expenses/cell-entries")
def set_cell_entries(data: CellEntries, db=Depends(get_db_dep)):
    """Replace all entries of a category/day cell in one go (sub-category + amount + note per line)."""
    month = parse_month(data.date[:7])[0]
    try:
        existing = {r["id"]: r for r in db.execute(
            "SELECT * FROM expenses WHERE category_id=? AND date=?", (data.category_id, data.date)).fetchall()}
        lines = [e for e in data.entries if e.amount != 0]
        for e in lines:
            if e.id is not None and e.id not in existing:
                raise HTTPException(status_code=400, detail="Entry does not belong to this cell")
            keep = existing[e.id]["subcategory_id"] if e.id is not None else None
            if e.subcategory_id is not None and not sub_allowed(db, data.category_id, e.subcategory_id, month, keep):
                raise HTTPException(status_code=400, detail="Sub-category is not valid for this category and month")
        if any(e.id is None for e in lines):
            ensure_category_open(db, data.category_id, month)
        keep_ids = {e.id for e in lines if e.id is not None}
        for eid in existing:
            if eid not in keep_ids:
                db.execute("DELETE FROM expenses WHERE id=?", (eid,))
        for e in lines:
            if e.id is not None:
                db.execute("UPDATE expenses SET subcategory_id=?, amount=?, note=? WHERE id=?",
                           (e.subcategory_id, e.amount, e.note.strip(), e.id))
            else:
                db.execute("""INSERT INTO expenses (category_id, user_id, date, amount, note, cashback, subcategory_id)
                              VALUES (?,1,?,?,?,0,?)""", (data.category_id, data.date, e.amount, e.note.strip(), e.subcategory_id))
        db.commit()
    except HTTPException:
        try:  # helpers may already have closed the connection
            db.rollback()
            db.close()
        except Exception:
            pass
        raise
    db.close()
    return {"ok": True}


@router.post("/expenses/range", status_code=201)
def set_expense_range(data: RangeSet, db=Depends(get_db_dep)):
    """Set the amount of a category on every day from start_day to end_day of a month.

    mode 'add' adds a new entry on each day. mode 'replace' (default) first removes existing entries: only the
    sub-category's own when one is given, otherwise the whole day cell."""
    year, mon = map(int, data.month.split("-"))
    days_in = calendar.monthrange(year, mon)[1]
    if data.amount <= 0 or data.start_day > data.end_day:
        raise HTTPException(status_code=400, detail="Invalid amount or day range")
    start = max(1, data.start_day)
    end = min(days_in, data.end_day)
    ensure_category_open(db, data.category_id, data.month)
    ensure_sub_ok(db, data.category_id, data.subcategory_id, data.month)
    for day in range(start, end + 1):
        dt = f"{data.month}-{day:02d}"
        if data.mode == "add":
            pass
        elif data.subcategory_id is None:
            db.execute("DELETE FROM expenses WHERE category_id=? AND date=?", (data.category_id, dt))
        else:
            db.execute("DELETE FROM expenses WHERE category_id=? AND date=? AND subcategory_id=?",
                       (data.category_id, dt, data.subcategory_id))
        db.execute("INSERT INTO expenses (category_id, user_id, date, amount, note, subcategory_id) VALUES (?,1,?,?,?,?)",
                   (data.category_id, dt, data.amount, data.note.strip(), data.subcategory_id))
    db.commit()
    db.close()
    return {"ok": True, "days": end - start + 1}


@router.post("/expenses", status_code=201)
def create_expense(data: ExpenseCreate, db=Depends(get_db_dep)):
    ensure_category_open(db, data.category_id, data.date[:7])
    ensure_sub_ok(db, data.category_id, data.subcategory_id, data.date[:7])
    cur = db.execute("""INSERT INTO expenses (category_id, user_id, date, amount, note, cashback, subcategory_id)
        VALUES (?,?,?,?,?,?,?)""",
        (data.category_id, data.user_id, data.date, data.amount, data.note, data.cashback, data.subcategory_id))
    db.commit()
    row = db.execute("""SELECT e.*, c.name as cat_name, c.icon, c.color
        FROM expenses e JOIN categories c ON c.id=e.category_id WHERE e.id=?""", (cur.lastrowid,)).fetchone()
    db.close()
    return dict(row)


@router.put("/expenses/{eid}")
def update_expense(eid: int, data: ExpenseUpdate, db=Depends(get_db_dep)):
    ensure_category_open(db, data.category_id, data.date[:7])
    cur_row = db.execute("SELECT subcategory_id FROM expenses WHERE id=?", (eid,)).fetchone()
    ensure_sub_ok(db, data.category_id, data.subcategory_id, data.date[:7], cur_row["subcategory_id"] if cur_row else None)
    db.execute("""UPDATE expenses SET category_id=?, date=?, amount=?, note=?, cashback=?, subcategory_id=? WHERE id=?""",
               (data.category_id, data.date, data.amount, data.note, data.cashback, data.subcategory_id, eid))
    db.commit()
    row = db.execute("""SELECT e.*, c.name as cat_name, c.icon, c.color
        FROM expenses e JOIN categories c ON c.id=e.category_id WHERE e.id=?""", (eid,)).fetchone()
    db.close()
    return dict(row) if row else {"error": "Not found"}


@router.delete("/expenses/{eid}")
def delete_expense(eid: int, db=Depends(get_db_dep)):
    db.execute("DELETE FROM expenses WHERE id=?", (eid,))
    db.commit()
    db.close()
    return {"ok": True}


@router.get("/dashboard")
def get_dashboard(month: str = Query(None), db=Depends(get_db_dep)):
    month, _, _ = parse_month(month)

    budget = budget_for_month(db, month)
    income = budget["income"]
    budget_cap = budget["budget_cap"]

    expenses = db.execute("""
        SELECT e.*, c.name as cat_name, c.icon, c.color
        FROM expenses e JOIN categories c ON c.id=e.category_id
        WHERE e.date LIKE ?""", (f"{month}-%",)).fetchall()
    cats = categories_for_month(db, month)

    cat_totals = {}
    cat_cashback = {}
    daily_totals = {}
    total_cashback = 0
    for e in expenses:
        cid = e["category_id"]
        cat_totals[cid] = cat_totals.get(cid, 0) + e["amount"]
        cat_cashback[cid] = cat_cashback.get(cid, 0) + e["cashback"]
        d = int(e["date"].split("-")[2])
        daily_totals[d] = daily_totals.get(d, 0) + e["amount"]
        total_cashback += e["cashback"]

    total_spent = sum(cat_totals.values())
    biggest_cat = max(cat_totals, key=cat_totals.get) if cat_totals else None
    biggest_cat_row = None
    if biggest_cat:
        for c in cats:
            if c["id"] == biggest_cat:
                biggest_cat_row = c
                break

    year, mon = map(int, month.split("-"))
    days = calendar.monthrange(year, mon)[1]
    daily_list = [round(daily_totals.get(d, 0)) for d in range(1, days + 1)]

    # 12 months ending at the selected one: spend and the budget cap that applied in each month
    y, m = year, mon
    months = []
    for _ in range(12):
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    months.reverse()
    sums = {r["ym"]: r["t"] for r in db.execute(
        "SELECT substr(date,1,7) AS ym, SUM(amount) AS t FROM expenses WHERE substr(date,1,7) BETWEEN ? AND ? GROUP BY ym",
        (months[0], months[-1])).fetchall()}
    trend = [{"month": mm, "total": round(sums.get(mm, 0)), "budget_cap": round(budget_for_month(db, mm)["budget_cap"])} for mm in months]

    prev = months[-2]
    prev_rows = db.execute("SELECT category_id, date, amount FROM expenses WHERE date LIKE ?", (f"{prev}-%",)).fetchall()
    prev_days = calendar.monthrange(int(prev[:4]), int(prev[5:]))[1]
    prev_daily = [0] * prev_days
    prev_cat = {}
    for r in prev_rows:
        prev_daily[int(r["date"][8:10]) - 1] += r["amount"]
        prev_cat[r["category_id"]] = prev_cat.get(r["category_id"], 0) + r["amount"]
    prev_daily = [round(v) for v in prev_daily]

    cat_breakdown = []
    for c in cats:
        cid = c["id"]
        spent = cat_totals.get(cid, 0)
        pct = round(spent / income * 100, 2) if income else 0
        cat_breakdown.append({**c, "spent": round(spent), "pct": pct, "prev_spent": round(prev_cat.get(cid, 0))})

    sub_rows = db.execute("""
        SELECT e.category_id, e.subcategory_id, s.name AS name, ROUND(SUM(e.amount)) AS spent
        FROM expenses e LEFT JOIN subcategories s ON s.id=e.subcategory_id
        WHERE e.date LIKE ? GROUP BY e.category_id, e.subcategory_id ORDER BY spent DESC""", (f"{month}-%",)).fetchall()
    subcategories = [{**dict(r), "name": r["name"] or "Unassigned"} for r in sub_rows]

    nxt = next_month(month)
    next_total = db.execute("SELECT COALESCE(SUM(amount),0) FROM expenses WHERE date LIKE ?", (f"{nxt}-%",)).fetchone()[0]
    top_rows = db.execute("""
        SELECT e.date, e.amount, e.note, c.name AS category, c.icon, s.name AS subcategory
        FROM expenses e JOIN categories c ON c.id=e.category_id LEFT JOIN subcategories s ON s.id=e.subcategory_id
        WHERE e.date LIKE ? AND e.amount > 0 ORDER BY e.amount DESC, e.date LIMIT 5""", (f"{month}-%",)).fetchall()
    unassigned = db.execute("SELECT COUNT(*) FROM expenses WHERE date LIKE ? AND subcategory_id IS NULL AND amount <> 0 AND category_id IN (SELECT category_id FROM subcategories)",
                            (f"{month}-%",)).fetchone()[0]
    db.close()
    return {
        "month": month,
        "income": income,
        "savings_amount": round(budget["savings_amount"]),
        "top_expenses": [dict(r) for r in top_rows],
        "unassigned_count": unassigned,
        "next_month": nxt,
        "next_total": round(next_total),
        "prev2_month": months[-3],
        "prev2_total": trend[-3]["total"],
        "prev_month": prev,
        "prev_total": round(sum(prev_daily)),
        "prev_daily": prev_daily,
        "budget_cap": round(budget_cap),
        "subcategories": subcategories,
        "total_spent": round(total_spent),
        "total_cashback": round(total_cashback),
        "biggest_cat": biggest_cat_row,
        "biggest_cat_amt": round(cat_totals.get(biggest_cat, 0)) if biggest_cat else 0,
        "extra_saving": round(income - total_spent),
        "daily": daily_list,
        "trend": trend,
        "categories": cat_breakdown,
    }


@router.get("/forecast")
def get_forecast(month: str = Query(None), db=Depends(get_db_dep)):
    month, _, _ = parse_month(month)
    try:
        return build_forecast(db, month)
    finally:
        db.close()

