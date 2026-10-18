import json
from datetime import date
from accrual import auto_value, is_auto
from sip import apply_due_sips, set_sip
import portfolio as pf
import prices as px
import ledger as led
from database import budget_for_month, current_month
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from ._common import row_dict as _row_dict
from sqlalchemy import func
from db import failover
from db.engine import SessionLocal, get_session
from db.models import Holding, HoldingGroup, PortfolioGoal, PortfolioSnapshot
from db.models.portfolio import AppPref, LedgerTransaction, SipLog

router = APIRouter(prefix="/spendlens/api", tags=["portfolio"])


class HoldingCreate(BaseModel):
    name: str
    ticker: str = ""
    asset_type: str = "EQ"
    sector: str = ""
    qty: float = 0
    buy_price: float = 0
    cmp: float = 0
    week52_low: float = 0
    week52_high: float = 0
    notes: str = ""
    tags: str = ""
    exposure: str = ""
    grp: str = ""
    sip_amount: float = 0
    sip_day: int = 0
    maturity: str = ""
    rate: float = 0
    start_date: str = ""
    compounding: str = "Q"
    rd: int = 0
    credits: str = ""
    manual: int = 0


class HoldingUpdate(BaseModel):
    name: str
    ticker: str = ""
    asset_type: str = "EQ"
    sector: str = ""
    qty: float = 0
    buy_price: float = 0
    cmp: float = 0
    week52_low: float = 0
    week52_high: float = 0
    notes: str = ""
    tags: str = ""
    exposure: str = ""
    grp: str = ""
    sip_amount: float = 0
    sip_day: int = 0
    maturity: str = ""
    rate: float = 0
    start_date: str = ""
    compounding: str = "Q"
    rd: int = 0
    credits: str = ""
    manual: int = 0
    visible: int = 1


class HoldingGroupIn(BaseModel):
    name: str


class HoldingMove(BaseModel):
    ids: list[int]
    grp: str = ""


def _group_name(raw):
    name = " ".join((raw or "").split())
    if not name:
        raise HTTPException(400, "Name is required")
    if name.lower() == "others":
        raise HTTPException(400, "'Others' is built in and cannot be used as a group name")
    return name


@router.get("/holding-groups")
def list_holding_groups(session=Depends(get_session)):
    apply_due_sips(session)
    held = _all_holdings(session)
    groups = []
    for g in session.query(HoldingGroup).order_by(HoldingGroup.sort_order, HoldingGroup.id).all():
        m = [h for h in held if h["grp"] == g.name]
        groups.append({"id": g.id, "name": g.name, "count": len(m), "present": round(sum(h["present"] for h in m), 2),
                       "hidden_columns": _csv(g.hidden_columns)})
    o = [h for h in held if not h["grp"]]
    return {"groups": groups, "others": {"count": len(o), "present": round(sum(h["present"] for h in o), 2)}}


def _csv(text):
    return [x for x in (text or "").split(",") if x]


class ColumnKeys(BaseModel):
    keys: list[str] = []


@router.put("/holding-groups/{gid}/hidden-columns")
def set_group_hidden_columns(gid: int, data: ColumnKeys, session=Depends(get_session)):
    """Columns of the Holdings table this group leaves empty (keys come from the UI's column list)."""
    g = session.get(HoldingGroup, gid)
    if not g:
        raise HTTPException(404, "Group not found")
    g.hidden_columns = ",".join(dict.fromkeys(k.strip() for k in data.keys if k.strip()))
    session.commit()
    return {"ok": True}


class HoldingColumnsIn(BaseModel):
    order: list[str] = []
    hidden: list[str] = []


@router.get("/holding-columns")
def get_holding_columns(session=Depends(get_session)):
    """Which Holdings-table columns show and in what order; empty until set in Admin (the UI then uses its own list)."""
    row = session.get(AppPref, "holding_columns")
    return json.loads(row.value) if row and row.value else {"order": [], "hidden": []}


@router.put("/holding-columns")
def set_holding_columns(data: HoldingColumnsIn, session=Depends(get_session)):
    value = json.dumps({"order": data.order, "hidden": data.hidden})
    row = session.get(AppPref, "holding_columns")
    if row:
        row.value = value
    else:
        session.add(AppPref(key="holding_columns", value=value))
    session.commit()
    return {"ok": True}


@router.post("/holding-groups", status_code=201)
def create_holding_group(data: HoldingGroupIn, session=Depends(get_session)):
    name = _group_name(data.name)
    if session.query(HoldingGroup).filter(HoldingGroup.name.ilike(name)).first():
        raise HTTPException(409, "A group with that name already exists")
    nxt = (session.query(func.max(HoldingGroup.sort_order)).scalar() or -1) + 1
    g = HoldingGroup(name=name, sort_order=nxt)
    session.add(g)
    session.commit()
    return {"id": g.id, "name": name}


@router.put("/holding-groups/{gid}")
def rename_holding_group(gid: int, data: HoldingGroupIn, session=Depends(get_session)):
    old = session.get(HoldingGroup, gid)
    if not old:
        raise HTTPException(404, "Group not found")
    name = _group_name(data.name)
    if session.query(HoldingGroup).filter(HoldingGroup.name.ilike(name), HoldingGroup.id != gid).first():
        raise HTTPException(409, "A group with that name already exists")
    old_name = old.name
    old.name = name
    session.query(Holding).filter(Holding.grp == old_name).update({"grp": name}, synchronize_session=False)
    session.commit()
    return {"ok": True}


@router.delete("/holding-groups/{gid}")
def delete_holding_group(gid: int, session=Depends(get_session)):
    """Deleting a group parks its holdings in Others (grp = '')."""
    g = session.get(HoldingGroup, gid)
    if not g:
        raise HTTPException(404, "Group not found")
    moved = session.query(Holding).filter(Holding.grp == g.name).update({"grp": ""}, synchronize_session=False)
    session.delete(g)
    session.commit()
    return {"ok": True, "moved": moved}


class SipIn(BaseModel):
    sip_amount: float = 0
    sip_day: int = 0


@router.put("/holdings/{hid}/sip")
def set_holding_sip(hid: int, data: SipIn, session=Depends(get_session)):
    if data.sip_amount < 0 or not 0 <= data.sip_day <= 31:
        raise HTTPException(400, "SIP amount must be positive and the day between 1 and 31")
    if not set_sip(session, hid, data.sip_amount, data.sip_day):
        raise HTTPException(404, "Holding not found")
    session.commit()
    return {"ok": True}


@router.get("/sip-log")
def sip_log(limit: int = Query(30), session=Depends(get_session)):
    rows = session.query(SipLog).order_by(SipLog.sip_date.desc(), SipLog.id.desc()).limit(limit).all()
    return [_row_dict(r) for r in rows]


@router.post("/holdings/move")
def move_holdings(data: HoldingMove, session=Depends(get_session)):
    grp = data.grp
    if grp and not session.query(HoldingGroup).filter(HoldingGroup.name == grp).first():
        raise HTTPException(400, "Unknown group")
    if data.ids:
        session.query(Holding).filter(Holding.id.in_(data.ids)).update({"grp": grp}, synchronize_session=False)
    session.commit()
    return {"ok": True, "moved": len(data.ids)}


def _holding_out(session, row):
    """Holding as the API returns it: stored fields plus invested / present / P&L, with auto-valued fixed-return rows."""
    h = dict(row)
    h.pop("sip_reminder", None)   # reminders-only flag, not part of the holding
    h["invested"] = round(h["qty"] * h["buy_price"], 2)
    h["auto"] = is_auto(h)
    if h["auto"]:
        sips = [(d, a) for d, a in session.query(SipLog.sip_date, SipLog.amount)
                .filter(SipLog.holding_id == h["id"]).order_by(SipLog.id)]
        pv, inv = auto_value(h, sips)
        h["present"], h["invested"] = round(pv, 2), round(inv, 2)
        h["cmp"] = round(pv / h["qty"], 4) if h["qty"] else h["cmp"]
    else:
        h["present"] = round(h["qty"] * h["cmp"], 2)
    # units held: shares / grams / ETF units = qty; funds = stored units, else worked out from value / NAV; FD, PF, cash = none
    if h["asset_type"] == "MF":
        h["units_held"] = h.get("units") or (round(h["present"] / h["nav"], 4) if (h.get("nav") or 0) > 0 else None)
    else:
        h["units_held"] = h["qty"] if h["asset_type"] in ("EQ", "GOLD") and h["qty"] else None
    h["pl"] = round(h["present"] - h["invested"], 2)
    h["pl_pct"] = round((h["pl"] / h["invested"] * 100) if h["invested"] else 0, 2)
    return h


def _all_holdings(session, *order_by):
    """Every holding as the API returns it."""
    return [_holding_out(session, _row_dict(r)) for r in session.query(Holding).order_by(*order_by).all()]


@router.get("/holdings")
def get_holdings(type: str = Query(None), session=Depends(get_session)):
    apply_due_sips(session)
    q = session.query(Holding).order_by(Holding.id)
    if type and type != "ALL":
        q = q.filter(Holding.asset_type == type)
    result = [_holding_out(session, _row_dict(r)) for r in q.all()]
    if not type or type == "ALL":
        pf.record_snapshot(session, result)
    return result


@router.post("/holdings", status_code=201)
def create_holding(data: HoldingCreate, session=Depends(get_session)):
    h = Holding(
        name=data.name, ticker=data.ticker, asset_type=data.asset_type, sector=data.sector,
        qty=data.qty, buy_price=data.buy_price, cmp=data.cmp,
        week52_low=data.week52_low, week52_high=data.week52_high, notes=data.notes,
        tags=data.tags.strip(), exposure=data.exposure or pf.guess_exposure(data.model_dump())[0],
        grp=data.grp, sip_amount=data.sip_amount, maturity=data.maturity, rate=data.rate,
        start_date=data.start_date, compounding=data.compounding, rd=data.rd,
        credits=data.credits, manual=data.manual,
    )
    session.add(h)
    session.commit()
    set_sip(session, h.id, data.sip_amount, data.sip_day)
    session.commit()
    return _holding_out(session, _row_dict(h))


@router.put("/holdings/{hid}")
def update_holding(hid: int, data: HoldingUpdate, session=Depends(get_session)):
    h = session.get(Holding, hid)
    if not h:
        raise HTTPException(404, "Holding not found")
    h.name, h.ticker, h.asset_type, h.sector = data.name, data.ticker, data.asset_type, data.sector
    h.qty, h.buy_price, h.cmp = data.qty, data.buy_price, data.cmp
    h.week52_low, h.week52_high, h.notes = data.week52_low, data.week52_high, data.notes
    h.tags = data.tags.strip()
    h.exposure = data.exposure or h.exposure
    h.grp, h.sip_amount, h.maturity, h.rate = data.grp, data.sip_amount, data.maturity, data.rate
    h.start_date, h.compounding, h.rd = data.start_date, data.compounding, data.rd
    h.credits, h.manual, h.visible = data.credits, data.manual, data.visible
    # A fund's value follows units x NAV, so a value typed here must update the units or the next refresh would undo it.
    if h.asset_type == "MF" and h.scheme_code and (h.nav or 0) > 0 and not data.manual:
        value = data.qty * data.cmp
        if value > 0 and abs(value - (h.units or 0) * h.nav) > 1:
            h.units = round(value / h.nav, 4)
    set_sip(session, hid, data.sip_amount, data.sip_day)
    session.commit()
    return _holding_out(session, _row_dict(h))


@router.delete("/holdings/{hid}")
def delete_holding(hid: int, session=Depends(get_session)):
    h = session.get(Holding, hid)
    if h:
        session.delete(h)
        session.commit()
    return {"ok": True}


@router.get("/export/portfolio")
def export_portfolio_csv(session=Depends(get_session)):
    rows = _all_holdings(session, Holding.asset_type, Holding.id)
    lines = ["Name,Ticker,Type,Sector,Group,Qty,Buy Price,CMP,Invested,Present,P&L,P&L%"]
    for r in rows:
        lines.append(f"{r['name']},{r['ticker']},{r['asset_type']},{r['sector']},{r['grp']},{r['qty']},{r['buy_price']},{r['cmp']},{r['invested']},{r['present']},{r['pl']},{r['pl_pct']}%")
    return Response("\n".join(lines), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=portfolio.csv"})


# ---------------------------------------------------------------- portfolio dashboard
class GoalIn(BaseModel):
    name: str
    target_amount: float
    target_year: int


class PlanIn(BaseModel):
    targets: dict[str, float] | None = None
    assumptions: dict | None = None


def _plan(session):
    return {"targets": pf.get_plan(session, "targets", pf.DEFAULT_TARGETS),
            "assumptions": pf.get_plan(session, "assumptions", pf.DEFAULT_ASSUMPTIONS)}


@router.get("/portfolio/plan")
def portfolio_plan(session=Depends(get_session)):
    pf.ensure(session)
    goals = session.query(PortfolioGoal).order_by(PortfolioGoal.target_year, PortfolioGoal.id).all()
    groups = session.query(HoldingGroup).order_by(HoldingGroup.sort_order, HoldingGroup.id).all()
    return {**_plan(session), "goals": [_row_dict(g) for g in goals],
            "groups": [g.name for g in groups] + ["Others"]}


@router.put("/portfolio/plan")
def save_portfolio_plan(data: PlanIn, session=Depends(get_session)):
    pf.ensure(session)
    if data.targets is not None:
        if any(v < 0 for v in data.targets.values()) or abs(sum(data.targets.values()) - 100) > 0.5:
            raise HTTPException(status_code=400, detail="Target allocation must add up to 100%")
        pf.set_plan(session, "targets", data.targets)
    if data.assumptions is not None:
        pf.set_plan(session, "assumptions", data.assumptions)
    return {"ok": True}


@router.post("/portfolio/goals", status_code=201)
def add_goal(data: GoalIn, session=Depends(get_session)):
    pf.ensure(session)
    if not data.name.strip() or data.target_amount <= 0:
        raise HTTPException(status_code=400, detail="Goal needs a name and a positive amount")
    g = PortfolioGoal(name=data.name.strip(), target_amount=data.target_amount, target_year=data.target_year)
    session.add(g)
    session.commit()
    return {"id": g.id}


@router.put("/portfolio/goals/{gid}")
def update_goal(gid: int, data: GoalIn, session=Depends(get_session)):
    pf.ensure(session)
    g = session.get(PortfolioGoal, gid)
    if g:
        g.name, g.target_amount, g.target_year = data.name.strip(), data.target_amount, data.target_year
        session.commit()
    return {"ok": True}


@router.delete("/portfolio/goals/{gid}")
def delete_goal(gid: int, session=Depends(get_session)):
    pf.ensure(session)
    g = session.get(PortfolioGoal, gid)
    if g:
        session.delete(g)
        session.commit()
    return {"ok": True}


class MixPlan(BaseModel):
    targets: dict[str, float]
    returns: dict[str, float]
    years: int = 15
    reach_years: float = 5


@router.get("/portfolio/exposure")
def portfolio_exposure(session=Depends(get_session)):
    """Allocation by exposure (Equity / Gold / Debt incl. cash), exposure by group and tag breakdown."""
    pf.ensure(session)
    pf.seed_exposure(session)
    apply_due_sips(session)
    return pf.exposure_summary(_all_holdings(session), pf.mix_plan(session)["targets"])


@router.get("/portfolio/mix")
def portfolio_mix(session=Depends(get_session)):
    """Current SIP split, forecast, and the SIP split + date that reaches the admin target ratio."""
    pf.ensure(session)
    pf.seed_exposure(session)
    apply_due_sips(session)
    held = _all_holdings(session)
    plan = pf.mix_plan(session)
    return {**pf.mix_summary(held, plan), "reach_years": plan["reach_years"]}


@router.put("/portfolio/mix-plan")
def save_mix_plan(data: MixPlan, session=Depends(get_session)):
    pf.ensure(session)
    if set(data.targets) != set(pf.MIX) or any(v < 0 for v in data.targets.values()) or abs(sum(data.targets.values()) - 100) > 0.5:
        raise HTTPException(status_code=400, detail="Targets must be Equity, Gold and Debt and add up to 100%")
    if set(data.returns) != set(pf.MIX) or any(not -20 <= v <= 40 for v in data.returns.values()):
        raise HTTPException(status_code=400, detail="Expected returns must be between -20% and 40%")
    if not 1 <= data.years <= 30 or not 0.5 <= data.reach_years <= 30:
        raise HTTPException(status_code=400, detail="Years must be between 1 and 30 (reach-by between 0.5 and 30)")
    pf.set_plan(session, "mix_targets", data.targets)
    pf.set_plan(session, "mix_returns", data.returns)
    pf.set_plan(session, "mix_years", data.years)
    pf.set_plan(session, "mix_reach_years", data.reach_years)
    return {"ok": True}


@router.get("/portfolio/kpis")
def portfolio_kpis(session=Depends(get_session)):
    pf.ensure(session)
    apply_due_sips(session)
    held = _all_holdings(session, Holding.id)
    pf.record_snapshot(session, held)
    today = date.today()
    total = sum(h["present"] for h in held)
    invested = sum(h["invested"] for h in held)
    groups = pf.group_totals(held)
    plan = _plan(session)
    snaps = [{"snap_date": s.snap_date, "total": s.total, "invested": s.invested}
             for s in session.query(PortfolioSnapshot).order_by(PortfolioSnapshot.snap_date).all()]
    rets = pf.snapshot_returns(snaps, today)
    goals = [_row_dict(g) for g in session.query(PortfolioGoal).order_by(PortfolioGoal.target_year, PortfolioGoal.id).all()]
    sim, extra = pf.projection(groups, goals, plan["assumptions"], today)
    sip_total = sum(h.get("sip_amount") or 0 for h in held)
    income = budget_for_month(session, current_month())["income"]
    spend = pf.monthly_spend(session, today)
    em = groups.get(pf.EMERGENCY, {}).get("present", 0)
    locked = sum(h["present"] for h in held if h["asset_type"] == "PF")
    ledger = led.summary(session, held)
    last_ok = px.last_ok_run(session)
    return {
        "total": round(total, 2), "invested": round(invested, 2), "pl": round(total - invested, 2),
        "pl_pct": round((total - invested) / invested * 100, 2) if invested else 0,
        "returns": rets,
        "sip": {"monthly": round(sip_total), "yearly": round(sip_total * 12),
                "pct_of_portfolio": round(sip_total * 12 / total * 100, 1) if total else 0,
                "savings_rate": round(sip_total / income * 100, 1) if income else None, "income": income},
        "safety": {"emergency": round(em, 2), "monthly_spend": round(spend),
                   "cover_months": round(em / spend, 1) if spend else None},
        "locked_pct": round(locked / total * 100, 1) if total else 0,
        "groups": groups,
        "drift": pf.drift(groups, plan["targets"], total),
        "concentration": pf.concentration(held),
        "performers": pf.performers(held),
        "fixed": pf.fixed_income(held),
        "history": [{"date": s["snap_date"], "total": s["total"], "invested": s["invested"]} for s in snaps],
        "forecast": sim,
        "extra_sip_needed": extra,
        "ledger": {"xirr": ledger["xirr"]["portfolio"], "covered_pct": ledger["xirr"]["covered_pct"], "fy": ledger["current_fy"],
                   "dividends": next((f["dividends"] for f in ledger["fy"] if f["fy"] == ledger["current_fy"]), 0),
                   "realized": next((f["realized"] for f in ledger["fy"] if f["fy"] == ledger["current_fy"]), 0)},
        "prices": {"last_ok": last_ok.isoformat(timespec="seconds") if last_ok else None,
                   "auto_count": session.query(Holding).filter(Holding.auto_price == 1).count()},
        "assumptions": plan["assumptions"],
    }


# ---------------------------------------------------------------- daily prices
class PriceCfg(BaseModel):
    ticker: str = ""
    scheme_code: str = ""
    units: float = 0
    auto_price: int = 0


def refresh_and_snapshot(only_if_stale=False):
    """Refresh auto prices, apply due SIPs and store today's portfolio snapshot. Used by the scheduler and the button.
    Opens its own session, since the scheduler calls it from a background thread."""
    if failover.read_only():  # PostgreSQL is down: nothing can be saved, so skip until it is back
        return None
    session = SessionLocal()
    try:
        if only_if_stale and not px.is_stale(session):
            return None
        out = px.run_refresh(session)
        apply_due_sips(session)
        pf.record_snapshot(session, _all_holdings(session, Holding.id))
        return out
    finally:
        session.close()


def _price_row(session, h):
    o = _holding_out(session, h)
    return {k: o[k] for k in ("id", "name", "asset_type", "grp", "ticker", "scheme_code", "units", "nav", "auto_price", "price_date",
                              "price_note", "present", "invested", "cmp", "week52_low", "week52_high")}


@router.get("/prices/status")
def prices_status(session=Depends(get_session)):
    apply_due_sips(session)
    runs = px.recent_runs(session)
    last = px.last_ok_run(session)
    q = session.query(Holding).filter(Holding.asset_type.in_(("EQ", "MF", "GOLD"))).order_by(Holding.asset_type.desc(), Holding.id)
    rows = [_price_row(session, _row_dict(h)) for h in q.all()]
    return {"last_ok": last.isoformat(timespec="seconds") if last else None, "stale": px.is_stale(session), "runs": runs, "holdings": rows}


@router.post("/prices/refresh")
def prices_refresh():
    return refresh_and_snapshot() or {}


@router.put("/prices/holding/{hid}")
def prices_set(hid: int, data: PriceCfg, session=Depends(get_session)):
    h = session.get(Holding, hid)
    if not h:
        raise HTTPException(404, "Holding not found")
    if data.auto_price and h.asset_type in ("EQ", "GOLD") and not data.ticker.strip():
        raise HTTPException(400, "Enter the NSE symbol first")
    if data.auto_price and h.asset_type == "MF" and not (data.scheme_code.strip() and data.units > 0):
        raise HTTPException(400, "Mutual funds need a scheme code and units")
    h.ticker = data.ticker.strip().upper()
    h.scheme_code = data.scheme_code.strip()
    h.units = data.units
    h.auto_price = 1 if data.auto_price else 0
    session.commit()
    return {"ok": True}


@router.get("/prices/suggest/{hid}")
def prices_suggest(hid: int, session=Depends(get_session)):
    h = session.get(Holding, hid)
    if not h:
        raise HTTPException(404, "Holding not found")
    try:
        if h.asset_type == "MF":
            return {"type": "MF", "options": px.scheme_candidates(px.fetch_amfi(), h.name)}
        return {"type": "EQ", "options": px.yahoo_search(h.name)}
    except Exception as e:
        raise HTTPException(502, f"Could not reach the price source: {str(e)[:100]}")


@router.post("/prices/units-from-value/{hid}")
def prices_units(hid: int, session=Depends(get_session)):
    """Set units = present value / today's NAV, so the current figure is kept and tracked from now on."""
    h = session.get(Holding, hid)
    if not h or h.asset_type != "MF" or not h.scheme_code:
        raise HTTPException(400, "Pick a scheme code first")
    try:
        s = px.fetch_amfi().get(h.scheme_code)
    except Exception as e:
        raise HTTPException(502, f"Could not reach AMFI: {str(e)[:100]}")
    if not s:
        raise HTTPException(400, "Scheme code not found in the AMFI file")
    value = _holding_out(session, _row_dict(h))["present"]
    units = round(value / s["nav"], 4)
    h.units, h.nav, h.price_date = units, s["nav"], s["date"]
    session.commit()
    return {"units": units, "nav": s["nav"]}


@router.post("/prices/auto-map")
def prices_auto_map(session=Depends(get_session)):
    """Fill missing NSE symbols (kept only if the live price is within 35% of the stored one) and AMFI scheme codes."""
    mapped, skipped = [], []
    try:
        amfi = px.fetch_amfi()
    except Exception:
        amfi = {}
    for h in session.query(Holding).filter(Holding.asset_type.in_(("EQ", "MF")), Holding.auto_price == 0).all():
        if h.asset_type == "MF":
            if not h.scheme_code and amfi:
                c = px.scheme_candidates(amfi, h.name, 1)
                if c:
                    h.scheme_code = c[0]["code"]
                    mapped.append(h.name)
                else:
                    skipped.append(h.name)
        elif not h.ticker:
            try:
                for cand in px.yahoo_search(h.name)[:3]:
                    q = px.yahoo_quote(cand["ticker"])
                    if h.cmp and abs(q["price"] / h.cmp - 1) <= 0.35:
                        h.ticker = cand["ticker"]
                        mapped.append(h.name)
                        break
                else:
                    skipped.append(h.name)
            except Exception:
                skipped.append(h.name)
    session.commit()
    return {"mapped": mapped, "skipped": skipped}


# ---------------------------------------------------------------- transaction ledger
class TxIn(BaseModel):
    holding_id: int | None = None
    name: str = ""
    tx_date: str
    kind: str
    qty: float = 0
    price: float = 0
    amount: float = 0
    fees: float = 0
    note: str = ""
    apply: int = 0


@router.get("/transactions")
def list_transactions(holding_id: int = Query(None), kind: str = Query(None), fy: str = Query(None), limit: int = 500,
                      session=Depends(get_session)):
    rows = [_row_dict(t) for t in session.query(LedgerTransaction)
            .order_by(LedgerTransaction.tx_date.desc(), LedgerTransaction.id.desc()).all()]
    if holding_id:
        rows = [r for r in rows if r["holding_id"] == holding_id]
    if kind:
        rows = [r for r in rows if r["kind"] == kind.upper()]
    if fy:
        rows = [r for r in rows if led.fy_of(r["tx_date"]) == fy]
    return {"total": len(rows), "rows": [{**r, "fy": led.fy_of(r["tx_date"])} for r in rows[:limit]]}


@router.post("/transactions", status_code=201)
def add_transaction(data: TxIn, session=Depends(get_session)):
    h = session.get(Holding, data.holding_id) if data.holding_id else None
    if data.holding_id and not h:
        raise HTTPException(404, "Holding not found")
    try:
        return {"id": led.add(session, data.model_dump(), _row_dict(h) if h else None)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/transactions/{tid}")
def delete_transaction(tid: int, session=Depends(get_session)):
    session.query(LedgerTransaction).filter(LedgerTransaction.id == tid).delete(synchronize_session=False)
    session.commit()
    return {"ok": True}


@router.get("/ledger/summary")
def ledger_summary(session=Depends(get_session)):
    apply_due_sips(session)
    return led.summary(session, _all_holdings(session, Holding.id))
