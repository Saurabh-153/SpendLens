"""The stock ledger (Ledger tab): positions / dividends / XIRR, the reconciliation audit, corporate-action events and
the Yahoo refresh. All under /equity, which auth maps to the ledger module. Broker files are imported from a folder
with `python spendlens/import_broker.py <folder>`, not through the API."""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import dividend_agent
import equity as eq
import equity_import as imp
from db.engine import get_session
from db.models import EquityAudit, EquityEvent, EquitySecurity, EquityTrade

router = APIRouter(prefix="/spendlens/api", tags=["equity"])


def _account(account):
    a = (account or "ALL").strip().upper()
    return None if a == "ALL" else a


@router.get("/equity/summary")
def equity_summary(account: str = Query("ALL"), session=Depends(get_session)):
    return eq.summary(session, _account(account))


@router.get("/equity/audit")
def equity_audit(account: str = Query("ALL"), session=Depends(get_session)):
    return eq.audit(session, _account(account))


@router.get("/equity/audit/{aid}")
def equity_audit_entry(aid: int, session=Depends(get_session)):
    a = session.get(EquityAudit, aid)
    if a is None:
        raise HTTPException(404, "Not found")
    return {"id": a.id, "at": a.at, "kind": a.kind, "account": a.account, "file_name": a.file_name, "summary": a.summary,
            "detail": json.loads(a.detail) if a.detail else None}


@router.get("/equity/stock/{symbol}")
def equity_stock(symbol: str, account: str = Query("ALL"), session=Depends(get_session)):
    return eq.stock_detail(session, symbol, _account(account))


@router.post("/equity/refresh")
def equity_refresh(session=Depends(get_session)):
    if not session.query(EquityTrade.id).first():
        raise HTTPException(400, "Import a tradebook first")
    return dividend_agent.refresh(session)


class EventIn(BaseModel):
    account: str = ""
    symbol: str
    ex_date: str
    kind: str
    ratio_new: float = 0
    ratio_old: float = 0
    qty: float = 0
    price: Optional[float] = None
    target_symbol: str = ""
    cost_pct: float = 0
    note: str = ""


def _clean_event(d: EventIn):
    kind = d.kind.strip().upper()
    if kind not in eq.KINDS:
        raise HTTPException(400, "Unknown event type")
    try:
        imp._iso(d.ex_date)
    except imp.ImportError_:
        raise HTTPException(400, "Enter a valid date")
    sym = d.symbol.strip().upper()
    if not sym:
        raise HTTPException(400, "Enter the symbol")
    if kind in ("SPLIT", "BONUS", "MERGER") and (d.ratio_new <= 0 or d.ratio_old <= 0):
        raise HTTPException(400, "Enter the ratio")
    if kind in ("DEMERGER", "MERGER", "RENAME") and not d.target_symbol.strip():
        raise HTTPException(400, "Enter the new symbol")
    if kind in ("IPO", "TRANSFER_IN", "BUYBACK", "TRANSFER_OUT") and d.qty <= 0:
        raise HTTPException(400, "Enter the quantity")
    if kind == "ADJUST" and d.qty == 0:
        raise HTTPException(400, "Enter the quantity (negative to remove shares)")
    if d.price is not None and d.price < 0:
        raise HTTPException(400, "Price can't be negative")
    if not 0 <= d.cost_pct <= 100:
        raise HTTPException(400, "Cost split is a percentage")
    return dict(account=d.account.strip().upper(), symbol=sym, ex_date=imp._iso(d.ex_date), kind=kind,
                ratio_new=d.ratio_new, ratio_old=d.ratio_old, qty=d.qty, price=d.price,
                target_symbol=d.target_symbol.strip().upper(), cost_pct=d.cost_pct, note=d.note.strip()[:300])


@router.get("/equity/events")
def list_events(session=Depends(get_session)):
    return {"events": eq.all_events(session), "kinds": list(eq.KINDS)}


@router.post("/equity/events", status_code=201)
def add_event(d: EventIn, session=Depends(get_session)):
    vals = _clean_event(d)
    e = EquityEvent(source="manual", **vals)
    session.add(e)
    session.add(EquityAudit(kind="event", account=vals["account"], summary=f"Added {vals['kind']} {vals['symbol']} {vals['ex_date']}",
                            detail=json.dumps(vals)))
    session.commit()
    return {"id": e.id}


@router.put("/equity/events/{eid}")
def update_event(eid: int, d: EventIn, session=Depends(get_session)):
    e = session.get(EquityEvent, eid)
    if e is None:
        raise HTTPException(404, "Event not found")
    vals = _clean_event(d)
    before = eq._ev_dict(e)
    for k, v in vals.items():
        setattr(e, k, v)
    if e.source == "yahoo":
        e.source = "manual"
    session.add(EquityAudit(kind="event", account=vals["account"], summary=f"Changed {vals['kind']} {vals['symbol']} {vals['ex_date']}",
                            detail=json.dumps({"before": before, "after": vals})))
    session.commit()
    return {"ok": True}


@router.delete("/equity/events/{eid}")
def delete_event(eid: int, session=Depends(get_session)):
    e = session.get(EquityEvent, eid)
    if e is None:
        raise HTTPException(404, "Event not found")
    before = eq._ev_dict(e)
    session.delete(e)
    session.add(EquityAudit(kind="event", account=before["account"], summary=f"Deleted {before['kind']} {before['symbol']} {before['ex_date']}",
                            detail=json.dumps(before)))
    session.commit()
    return {"ok": True}


class SecurityIn(BaseModel):
    yahoo_symbol: str = ""


@router.put("/equity/securities/{symbol}")
def set_security(symbol: str, d: SecurityIn, session=Depends(get_session)):
    sym = symbol.strip().upper()
    s = session.query(EquitySecurity).filter(EquitySecurity.symbol == sym).first()
    if s is None:
        s = EquitySecurity(symbol=sym)
        session.add(s)
    s.yahoo_symbol = d.yahoo_symbol.strip().upper()
    session.commit()
    return {"ok": True}
