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
from database import (budget_caps_for_months, budget_for_month, categories_for_month, category_allowed_in_month,
                      current_month, next_month, prev_month)
from pydantic import BaseModel
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from sqlalchemy import exists, func, select
from ._common import row_dict as _row_dict
from db.engine import get_session
from db.models import Category, CategoryTarget, Subcategory, SubcategoryRule, BudgetHistory, Expense

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


def ensure_category_open(session, category_id, month):
    """Reject new spend on a category that is not active in that month (keeps history unchanged)."""
    parse_month(month)
    if not category_allowed_in_month(session, category_id, month):
        raise HTTPException(status_code=400, detail="Category is not active in " + month)


def ensure_sub_ok(session, category_id, sub_id, month, keep_sub_id=None):
    if sub_id is not None and not sub_allowed(session, category_id, sub_id, month, keep_sub_id):
        raise HTTPException(status_code=400, detail="Sub-category is not valid for this category and month")


def get_category_or_404(session, cid):
    cat = session.get(Category, cid)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    return cat


def has_expenses(session, **where):
    """True when at least one expense matches, e.g. has_expenses(session, category_id=3)."""
    q = session.query(Expense.id)
    for col, val in where.items():
        q = q.filter(getattr(Expense, col) == val)
    return q.first() is not None


def months_with_expenses_from(session, from_month=None, **where):
    """How many distinct months (at or after `from_month`, if given) hold a matching expense."""
    ym = func.substr(Expense.date, 1, 7)
    q = session.query(func.count(func.distinct(ym)))
    if from_month is not None:
        q = q.filter(ym >= from_month)
    for col, val in where.items():
        q = q.filter(getattr(Expense, col) == val)
    return q.scalar()


def _category_dict(cat, today, target_pct, has_data):
    row = _row_dict(cat)
    row["target_pct"] = target_pct
    row["status"] = category_status(row, today)
    row["has_data"] = has_data
    return row


def category_view(session, cid):
    today = current_month()
    cat = get_category_or_404(session, cid)
    t = session.query(CategoryTarget).filter(CategoryTarget.category_id == cid, CategoryTarget.from_month <= today) \
        .order_by(CategoryTarget.from_month.desc()).first()
    return _category_dict(cat, today, t.target_pct if t else 0, has_expenses(session, category_id=cid))


@router.get("/categories")
def get_categories(month: str = Query(None), session=Depends(get_session)):
    """Without `month`: every category with its lifecycle status. With `month`: those shown in that month."""
    if month:
        return categories_for_month(session, parse_month(month)[0])
    today = current_month()
    cats = session.query(Category).order_by(Category.sort_order, Category.id).all()
    # ascending, so the last row written per category is its latest target as of today
    targets = {t.category_id: t.target_pct for t in session.query(CategoryTarget)
               .filter(CategoryTarget.from_month <= today).order_by(CategoryTarget.from_month)}
    used = {r[0] for r in session.query(Expense.category_id).distinct()}
    return [_category_dict(c, today, targets.get(c.id, 0), c.id in used) for c in cats]


@router.post("/categories", status_code=201)
def create_category(data: CategoryCreate, session=Depends(get_session)):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    start = parse_month(data.start_month)[0]
    if session.query(Category).filter(func.lower(Category.name) == name.lower(), Category.end_month.is_(None)).first():
        raise HTTPException(status_code=409, detail="An active category with this name already exists")
    order = (session.query(func.max(Category.sort_order)).scalar() or 0) + 1
    cat = Category(name=name, icon=data.icon, color=data.color, target_pct=data.target_pct,
                    hint=data.hint, visible=1, sort_order=order, start_month=start)
    session.add(cat)
    session.flush()
    session.add(CategoryTarget(category_id=cat.id, from_month=start, target_pct=data.target_pct))
    session.commit()
    return category_view(session, cat.id)


@router.put("/categories/reorder")
def reorder_categories(data: ReorderRequest, session=Depends(get_session)):
    for i, cid in enumerate(data.ids, start=1):
        session.query(Category).filter(Category.id == cid).update({"sort_order": i}, synchronize_session=False)
    session.commit()
    return {"ok": True}


@router.put("/categories/{cid}")
def update_category(cid: int, data: CategoryUpdate, session=Depends(get_session)):
    """Rename / restyle. Label-only: applies to every month, no amounts change."""
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    cat = get_category_or_404(session, cid)
    cat.name, cat.icon, cat.color, cat.hint = name, data.icon, data.color, data.hint
    session.commit()
    return category_view(session, cid)


@router.post("/categories/{cid}/archive")
def archive_category(cid: int, data: ArchiveRequest, session=Depends(get_session)):
    """Hide a category from `from_month` onward (default next month); earlier months are unchanged."""
    from_month = parse_month(data.from_month or next_month(current_month()))[0]
    cat = get_category_or_404(session, cid)
    if from_month <= cat.start_month:
        raise HTTPException(status_code=400, detail="Archive month must be after the month the category starts")
    cat.end_month = prev_month(from_month)
    session.commit()
    later = months_with_expenses_from(session, from_month, category_id=cid)
    return {**category_view(session, cid), "months_with_data_after": later}


@router.post("/categories/{cid}/restore")
def restore_category(cid: int, session=Depends(get_session)):
    cat = get_category_or_404(session, cid)
    cat.end_month = None
    session.commit()
    return category_view(session, cid)


@router.get("/categories/{cid}/usage")
def category_usage(cid: int, session=Depends(get_session)):
    """What a category holds, so a delete can be double-checked: its entries, their total and date range, and what else
    would go with it. A category with entries can never be deleted (archive it instead)."""
    get_category_or_404(session, cid)
    n, total, first, last = session.query(
        func.count(Expense.id), func.coalesce(func.sum(Expense.amount), 0), func.min(Expense.date), func.max(Expense.date)
    ).filter(Expense.category_id == cid).one()
    months = months_with_expenses_from(session, category_id=cid)
    subs = session.query(Subcategory).filter(Subcategory.category_id == cid).count()
    targets = session.query(CategoryTarget).filter(CategoryTarget.category_id == cid).count()
    return {"entries": n, "total": round(total, 2), "first": first, "last": last, "months": months,
            "subcategories": subs, "target_changes": targets, "can_delete": n == 0}


@router.delete("/categories/{cid}")
def delete_category(cid: int, session=Depends(get_session)):
    """Hard delete only for categories that never had an expense; otherwise archive."""
    cat = get_category_or_404(session, cid)
    if has_expenses(session, category_id=cid):
        raise HTTPException(status_code=409, detail="Category has expense history - archive it instead")
    # With no expenses there is nothing to orphan. Its sub-categories and their rules go with it (they would otherwise
    # block the delete, since each refers to the category).
    session.query(SubcategoryRule).filter(SubcategoryRule.category_id == cid).delete(synchronize_session=False)
    session.query(Subcategory).filter(Subcategory.category_id == cid).delete(synchronize_session=False)
    session.query(CategoryTarget).filter(CategoryTarget.category_id == cid).delete(synchronize_session=False)
    session.delete(cat)
    session.commit()
    return {"ok": True}


@router.get("/categories/{cid}/targets")
def category_target_history(cid: int, session=Depends(get_session)):
    get_category_or_404(session, cid)
    rows = session.query(CategoryTarget).filter(CategoryTarget.category_id == cid) \
        .order_by(CategoryTarget.from_month).all()
    return [{"from_month": r.from_month, "target_pct": r.target_pct} for r in rows]


@router.put("/categories/{cid}/target")
def set_category_target(cid: int, data: TargetSet, session=Depends(get_session)):
    """Target % valid from `from_month` onward; earlier months keep their previous target."""
    month = parse_month(data.from_month)[0]
    if not 0 <= data.target_pct <= 100:
        raise HTTPException(status_code=400, detail="Target must be between 0 and 100")
    data.target_pct = round(data.target_pct, 8)   # keep enough precision that a typed rupee amount round-trips exactly
    get_category_or_404(session, cid)
    t = session.get(CategoryTarget, (cid, month))
    if t:
        t.target_pct = data.target_pct
    else:
        session.add(CategoryTarget(category_id=cid, from_month=month, target_pct=data.target_pct))
    session.commit()
    return {"ok": True}


@router.get("/budget")
def budget_history(session=Depends(get_session)):
    rows = session.query(BudgetHistory).order_by(BudgetHistory.from_month).all()
    return [{"from_month": r.from_month, "income": r.income, "savings_amount": r.savings_amount} for r in rows]


@router.put("/budget")
def set_budget(data: BudgetSet, session=Depends(get_session)):
    """Income / savings % valid from `from_month` onward."""
    month = parse_month(data.from_month)[0]
    if data.income < 0 or not 0 <= data.savings_amount <= data.income:
        raise HTTPException(status_code=400, detail="Savings must be between 0 and the salary")
    b = session.query(BudgetHistory).filter(BudgetHistory.from_month == month).first()
    if b:
        b.income, b.savings_amount = round(data.income, 2), round(data.savings_amount, 2)
    else:
        session.add(BudgetHistory(from_month=month, income=round(data.income, 2), savings_amount=round(data.savings_amount, 2)))
    session.commit()
    return {"ok": True}


def get_sub_or_404(session, sid):
    sub = session.get(Subcategory, sid)
    if not sub:
        raise HTTPException(status_code=404, detail="Sub-category not found")
    return sub


def _sub_dict(sub, today, has_data):
    d = _row_dict(sub)
    d["status"] = subcategory_status(d, today)
    d["has_data"] = has_data
    return d


def sub_view(session, sid):
    return _sub_dict(get_sub_or_404(session, sid), current_month(), has_expenses(session, subcategory_id=sid))


@router.get("/subcategories")
def get_subcategories(category_id: int = Query(None), month: str = Query(None), session=Depends(get_session)):
    """With `month`: those usable/shown in that month. Without: all, with lifecycle status."""
    if month:
        return subcategories_for_month(session, parse_month(month)[0], category_id)
    q = session.query(Subcategory)
    if category_id:
        q = q.filter(Subcategory.category_id == category_id)
    subs = q.order_by(Subcategory.category_id, Subcategory.sort_order, Subcategory.id).all()
    used = {r[0] for r in session.query(Expense.subcategory_id).filter(Expense.subcategory_id.isnot(None)).distinct()}
    today = current_month()
    return [_sub_dict(s, today, s.id in used) for s in subs]


@router.post("/subcategories", status_code=201)
def create_subcategory(data: SubCreate, session=Depends(get_session)):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    start = parse_month(data.start_month)[0]
    get_category_or_404(session, data.category_id)
    if session.query(Subcategory).filter(Subcategory.category_id == data.category_id,
                                          func.lower(Subcategory.name) == name.lower(),
                                          Subcategory.end_month.is_(None)).first():
        raise HTTPException(status_code=409, detail="This category already has an active sub-category with that name")
    order = (session.query(func.max(Subcategory.sort_order)).filter(Subcategory.category_id == data.category_id).scalar() or 0) + 1
    sub = Subcategory(category_id=data.category_id, name=name, sort_order=order, start_month=start)
    session.add(sub)
    session.commit()
    return sub_view(session, sub.id)


@router.put("/subcategories/reorder")
def reorder_subcategories(data: ReorderRequest, session=Depends(get_session)):
    for i, sid in enumerate(data.ids, start=1):
        session.query(Subcategory).filter(Subcategory.id == sid).update({"sort_order": i}, synchronize_session=False)
    session.commit()
    return {"ok": True}


@router.get("/subcategories/review")
def subcategory_review(session=Depends(get_session)):
    """Entries without a sub-category, grouped by category + note, for the Admin 'Needs review' list."""
    rows = (session.query(Expense.id, Expense.category_id, Category.name.label("category"), Expense.note, Expense.amount)
            .join(Category, Category.id == Expense.category_id)
            .filter(Expense.subcategory_id.is_(None),
                    exists().where(Subcategory.category_id == Expense.category_id))
            .order_by(Category.sort_order, Expense.id).all())
    groups = {}
    for r in rows:
        key = (r.category_id, normalize(r.note))
        g = groups.setdefault(key, {"category_id": r.category_id, "category": r.category, "note": key[1], "count": 0, "total": 0})
        g["count"] += 1
        g["total"] += r.amount
    return sorted(groups.values(), key=lambda g: (-g["count"], g["category"]))


@router.post("/subcategories/review/map")
def subcategory_review_map(data: ReviewMap, session=Depends(get_session)):
    """Assign a sub-category to every unmapped entry with this note, and remember the note as a rule."""
    sub = session.get(Subcategory, data.subcategory_id)
    if not sub or sub.category_id != data.category_id:
        raise HTTPException(status_code=400, detail="Sub-category does not belong to this category")
    note = normalize(data.note)
    ids = [r.id for r in session.query(Expense.id, Expense.note)
           .filter(Expense.category_id == data.category_id, Expense.subcategory_id.is_(None)).all()
           if normalize(r.note) == note]
    for i in range(0, len(ids), 500):
        session.query(Expense).filter(Expense.id.in_(ids[i:i + 500])).update(
            {"subcategory_id": data.subcategory_id}, synchronize_session=False)
    session.commit()
    if note and not session.query(SubcategoryRule).filter(SubcategoryRule.category_id == data.category_id,
                                                           SubcategoryRule.pattern == note,
                                                           SubcategoryRule.match_type == "exact").first():
        session.add(SubcategoryRule(category_id=data.category_id, pattern=note, match_type="exact",
                                     subcategory_id=data.subcategory_id))
        session.commit()
    return {"updated": len(ids)}


@router.put("/subcategories/{sid}")
def update_subcategory(sid: int, data: SubUpdate, session=Depends(get_session)):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    get_sub_or_404(session, sid).name = name
    session.commit()
    return sub_view(session, sid)


@router.post("/subcategories/{sid}/archive")
def archive_subcategory(sid: int, data: ArchiveRequest, session=Depends(get_session)):
    from_month = parse_month(data.from_month or next_month(current_month()))[0]
    sub = get_sub_or_404(session, sid)
    if from_month <= sub.start_month:
        raise HTTPException(status_code=400, detail="Archive month must be after the month the sub-category starts")
    sub.end_month = prev_month(from_month)
    session.commit()
    later = months_with_expenses_from(session, from_month, subcategory_id=sid)
    return {**sub_view(session, sid), "months_with_data_after": later}


@router.post("/subcategories/{sid}/restore")
def restore_subcategory(sid: int, session=Depends(get_session)):
    get_sub_or_404(session, sid).end_month = None
    session.commit()
    return sub_view(session, sid)


@router.delete("/subcategories/{sid}")
def delete_subcategory(sid: int, session=Depends(get_session)):
    get_sub_or_404(session, sid)
    if has_expenses(session, subcategory_id=sid):
        raise HTTPException(status_code=409, detail="Sub-category has expenses - archive it instead")
    session.query(SubcategoryRule).filter(SubcategoryRule.subcategory_id == sid).delete(synchronize_session=False)
    session.query(Subcategory).filter(Subcategory.id == sid).delete(synchronize_session=False)
    session.commit()
    return {"ok": True}


def expense_out(row):
    """An expense joined to its category: the expense's columns, then the category's name, icon and colour."""
    e, cat_name, icon, color = row
    return {**_row_dict(e), "cat_name": cat_name, "icon": icon, "color": color}


def expense_with_category(session, eid):
    row = (session.query(Expense, Category.name, Category.icon, Category.color)
           .join(Category, Category.id == Expense.category_id).filter(Expense.id == eid).first())
    return expense_out(row) if row else None


@router.get("/expenses")
def get_expenses(month: str = Query(None), session=Depends(get_session)):
    q = session.query(Expense, Category.name, Category.icon, Category.color).join(Category, Category.id == Expense.category_id)
    if month:
        q = q.filter(Expense.date.like(f"{month}-%")).order_by(Expense.date, Expense.id)
    else:
        q = q.order_by(Expense.date.desc(), Expense.id.desc()).limit(200)
    return [expense_out(r) for r in q.all()]


@router.get("/expenses/months")
def get_expense_months(session=Depends(get_session)):
    ym = func.substr(Expense.date, 1, 7).label("m")
    return [r.m for r in session.query(ym).distinct().order_by(ym.desc()).all()]


@router.get("/expenses/monthly-grid")
def get_monthly_grid(month: str = Query(None), session=Depends(get_session)):
    month, year, mon = parse_month(month)
    days_in_month = calendar.monthrange(year, mon)[1]

    cats = categories_for_month(session, month)
    expenses = session.query(Expense).filter(Expense.date.like(f"{month}-%")).order_by(Expense.date, Expense.id).all()
    budget = budget_for_month(session, month)
    sub_list = subcategories_for_month(session, month)

    income = budget["income"]
    budget_cap = round(budget["budget_cap"])

    exp_map = {}
    for e in expenses:
        d = int(e.date.split("-")[2])
        key = (e.category_id, d)
        if key not in exp_map:
            exp_map[key] = {"amount": 0, "cashback": 0, "note": "", "expense_id": e.id, "entries": []}
        exp_map[key]["amount"] += e.amount
        exp_map[key]["cashback"] += e.cashback
        if e.note:
            existing = exp_map[key]["note"]
            exp_map[key]["note"] = (existing + "; " + e.note) if existing else e.note
        exp_map[key]["expense_id"] = e.id
        exp_map[key]["entries"].append({"id": e.id, "subcategory_id": e.subcategory_id, "amount": e.amount,
                                        "note": e.note, "cashback": e.cashback})

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
def get_expense(eid: int, session=Depends(get_session)):
    out = expense_with_category(session, eid)
    if not out:
        raise HTTPException(status_code=404, detail="Not found")
    return out


@router.put("/expenses/cell-entries")
def set_cell_entries(data: CellEntries, session=Depends(get_session)):
    """Replace all entries of a category/day cell in one go (sub-category + amount + note per line)."""
    month = parse_month(data.date[:7])[0]
    existing = {e.id: e for e in session.query(Expense).filter(Expense.category_id == data.category_id, Expense.date == data.date).all()}
    lines = [e for e in data.entries if e.amount != 0]
    for e in lines:
        if e.id is not None and e.id not in existing:
            raise HTTPException(status_code=400, detail="Entry does not belong to this cell")
        keep = existing[e.id].subcategory_id if e.id is not None else None
        if e.subcategory_id is not None and not sub_allowed(session, data.category_id, e.subcategory_id, month, keep):
            raise HTTPException(status_code=400, detail="Sub-category is not valid for this category and month")
    if any(e.id is None for e in lines):
        ensure_category_open(session, data.category_id, month)
    keep_ids = {e.id for e in lines if e.id is not None}
    for eid, row in existing.items():
        if eid not in keep_ids:
            session.delete(row)
    session.flush()   # deletes first, so new rows reuse ids exactly as they did when these ran one statement at a time
    for e in lines:
        if e.id is not None:
            row = existing[e.id]
            row.subcategory_id, row.amount, row.note = e.subcategory_id, e.amount, e.note.strip()
        else:
            session.add(Expense(category_id=data.category_id, user_id=1, date=data.date, amount=e.amount,
                                note=e.note.strip(), cashback=0, subcategory_id=e.subcategory_id))
    session.commit()
    return {"ok": True}


@router.post("/expenses/range", status_code=201)
def set_expense_range(data: RangeSet, session=Depends(get_session)):
    """Set the amount of a category on every day from start_day to end_day of a month.

    mode 'add' adds a new entry on each day. mode 'replace' (default) first removes existing entries: only the
    sub-category's own when one is given, otherwise the whole day cell."""
    year, mon = map(int, data.month.split("-"))
    days_in = calendar.monthrange(year, mon)[1]
    if data.amount <= 0 or data.start_day > data.end_day:
        raise HTTPException(status_code=400, detail="Invalid amount or day range")
    start = max(1, data.start_day)
    end = min(days_in, data.end_day)
    ensure_category_open(session, data.category_id, data.month)
    ensure_sub_ok(session, data.category_id, data.subcategory_id, data.month)
    for day in range(start, end + 1):
        dt = f"{data.month}-{day:02d}"
        if data.mode == "add":
            pass
        else:
            doomed = session.query(Expense).filter(Expense.category_id == data.category_id, Expense.date == dt)
            if data.subcategory_id is not None:
                doomed = doomed.filter(Expense.subcategory_id == data.subcategory_id)
            doomed.delete(synchronize_session=False)
        session.add(Expense(category_id=data.category_id, user_id=1, date=dt, amount=data.amount,
                            note=data.note.strip(), subcategory_id=data.subcategory_id))
        session.flush()   # one day at a time, so ids are handed out in the same order as before
    session.commit()
    return {"ok": True, "days": end - start + 1}


@router.post("/expenses", status_code=201)
def create_expense(data: ExpenseCreate, session=Depends(get_session)):
    ensure_category_open(session, data.category_id, data.date[:7])
    ensure_sub_ok(session, data.category_id, data.subcategory_id, data.date[:7])
    row = Expense(category_id=data.category_id, user_id=data.user_id, date=data.date, amount=data.amount,
                  note=data.note, cashback=data.cashback, subcategory_id=data.subcategory_id)
    session.add(row)
    session.commit()
    return expense_with_category(session, row.id)


@router.put("/expenses/{eid}")
def update_expense(eid: int, data: ExpenseUpdate, session=Depends(get_session)):
    ensure_category_open(session, data.category_id, data.date[:7])
    row = session.get(Expense, eid)
    ensure_sub_ok(session, data.category_id, data.subcategory_id, data.date[:7], row.subcategory_id if row else None)
    if row:
        row.category_id, row.date, row.amount, row.note = data.category_id, data.date, data.amount, data.note
        row.cashback, row.subcategory_id = data.cashback, data.subcategory_id
        session.commit()
    return expense_with_category(session, eid) or {"error": "Not found"}


@router.delete("/expenses/{eid}")
def delete_expense(eid: int, session=Depends(get_session)):
    session.query(Expense).filter(Expense.id == eid).delete(synchronize_session=False)
    session.commit()
    return {"ok": True}


@router.get("/dashboard")
def get_dashboard(month: str = Query(None), session=Depends(get_session)):
    month, _, _ = parse_month(month)

    budget = budget_for_month(session, month)
    income = budget["income"]
    budget_cap = budget["budget_cap"]

    expenses = (session.query(Expense).join(Category, Category.id == Expense.category_id)
                .filter(Expense.date.like(f"{month}-%")).all())
    cats = categories_for_month(session, month)

    cat_totals = {}
    cat_cashback = {}
    daily_totals = {}
    total_cashback = 0
    for e in expenses:
        cid = e.category_id
        cat_totals[cid] = cat_totals.get(cid, 0) + e.amount
        cat_cashback[cid] = cat_cashback.get(cid, 0) + e.cashback
        d = int(e.date.split("-")[2])
        daily_totals[d] = daily_totals.get(d, 0) + e.amount
        total_cashback += e.cashback

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
    ym = func.substr(Expense.date, 1, 7)
    sums = {r.ym: r.total for r in session.query(ym.label("ym"), func.sum(Expense.amount).label("total"))
            .filter(ym.between(months[0], months[-1])).group_by(ym).all()}
    caps = budget_caps_for_months(session, months)
    trend = [{"month": mm, "total": round(sums.get(mm, 0)), "budget_cap": round(caps[mm])} for mm in months]

    prev = months[-2]
    prev_rows = session.query(Expense.category_id, Expense.date, Expense.amount).filter(Expense.date.like(f"{prev}-%")).all()
    prev_days = calendar.monthrange(int(prev[:4]), int(prev[5:]))[1]
    prev_daily = [0] * prev_days
    prev_cat = {}
    for r in prev_rows:
        prev_daily[int(r.date[8:10]) - 1] += r.amount
        prev_cat[r.category_id] = prev_cat.get(r.category_id, 0) + r.amount
    prev_daily = [round(v) for v in prev_daily]

    cat_breakdown = []
    for c in cats:
        cid = c["id"]
        spent = cat_totals.get(cid, 0)
        pct = round(spent / income * 100, 2) if income else 0
        cat_breakdown.append({**c, "spent": round(spent), "pct": pct, "prev_spent": round(prev_cat.get(cid, 0))})

    spent_by_sub = func.round(func.sum(Expense.amount)).label("spent")
    sub_rows = (session.query(Expense.category_id, Expense.subcategory_id, Subcategory.name.label("name"), spent_by_sub)
                .outerjoin(Subcategory, Subcategory.id == Expense.subcategory_id)
                .filter(Expense.date.like(f"{month}-%"))
                .group_by(Expense.category_id, Expense.subcategory_id).order_by(spent_by_sub.desc()).all())
    subcategories = [{"category_id": r.category_id, "subcategory_id": r.subcategory_id,
                      "name": r.name or "Unassigned", "spent": r.spent} for r in sub_rows]

    nxt = next_month(month)
    next_total = session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.date.like(f"{nxt}-%")).scalar()
    top_rows = (session.query(Expense.date, Expense.amount, Expense.note, Category.name.label("category"), Category.icon,
                              Subcategory.name.label("subcategory"))
                .join(Category, Category.id == Expense.category_id)
                .outerjoin(Subcategory, Subcategory.id == Expense.subcategory_id)
                .filter(Expense.date.like(f"{month}-%"), Expense.amount > 0)
                .order_by(Expense.amount.desc(), Expense.date).limit(5).all())
    unassigned = (session.query(func.count(Expense.id))
                  .filter(Expense.date.like(f"{month}-%"), Expense.subcategory_id.is_(None), Expense.amount != 0,
                          Expense.category_id.in_(select(Subcategory.category_id))).scalar())
    return {
        "month": month,
        "income": income,
        "savings_amount": round(budget["savings_amount"]),
        "top_expenses": [r._asdict() for r in top_rows],
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
def get_forecast(month: str = Query(None), session=Depends(get_session)):
    month, _, _ = parse_month(month)
    return build_forecast(session, month)

