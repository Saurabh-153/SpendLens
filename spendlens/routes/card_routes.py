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

from ._common import get_db_dep, row_dict
from db.engine import get_session
from db.models import Card, CardMerchantRule

router = APIRouter(prefix="/spendlens/api", tags=["cards"])


# ----------------------------------------------------------------- credit cards

class MerchantRule(BaseModel):
    pattern: str
    cls: str                     # online / offline / excluded
    match_type: str = "contains"
    card_id: int | None = None


class CardSettings(BaseModel):
    name: str | None = None            # a card's display name
    profile: str | None = None         # reward scheme: sbi_cashback / icici_amazon / generic (usage only)
    credit_limit: float = 0
    annual_fee: float = 0
    fee_waiver_spend: float = 0
    cashback_cap: float = 0            # 0 = uncapped
    rates: dict[str, float]            # percent per reward class
    statement_day: int                 # day of month the statement is generated
    grace_days: int                    # days from the statement to the due date
    pay_buffer_days: int = 1           # how many days before the due date to pay
    float_rate: float = 7              # what idle money earns, % a year


@router.get("/cards")
def cards_list(db=Depends(get_db_dep)):
    """One entry per physical card, most recently used first. A card that was re-issued under a
    new number is one entry listing all its numbers."""
    try:
        return cards.list_cards(db)
    finally:
        db.close()


@router.get("/cards/overview")
def cards_overview(db=Depends(get_db_dep)):
    """Usage across every card: spend, cost, what is due next, and spend by financial year."""
    try:
        return cards.overview(db)
    finally:
        db.close()


@router.get("/cards/dashboard")
def cards_dashboard(card_id: int | None = None, db=Depends(get_db_dep)):
    """Spend, cashback earned vs computed, merchant breakdown, leakage and fee progress."""
    try:
        return cards.dashboard(db, card_id)
    finally:
        db.close()


@router.get("/cards/transactions")
def cards_transactions(card_id: int | None = None, limit: int = Query(500, le=5000), db=Depends(get_db_dep)):
    try:
        card = cards.get_card(db, card_id)
        if not card:
            return []
        return [dict(r) for r in db.execute(
            """SELECT t.*, s.period_to FROM card_txns t
               LEFT JOIN card_statements s ON s.id = t.statement_id
               WHERE t.card_id=? ORDER BY t.tx_date DESC, t.id DESC LIMIT ?""",
            (card["id"], limit))]
    finally:
        db.close()


@router.get("/cards/parsers")
def cards_parsers():
    """Which statement formats can be read, and whether the Claude fallback is switched on."""
    return {"formats": [n for n, _, _ in cards.PARSERS], "llm_available": cards.llm_available()}


MAX_UPLOAD = 15 * 1024 * 1024  # a statement is under 1 MB; this is a safety stop


@router.post("/cards/upload")
async def cards_upload(files: list[UploadFile] = File(...), password: str = Form(""),
                       use_llm: bool = Form(False), card_id: int | None = Form(None)):
    """Import uploaded statement PDFs. A file is checked (against its own purchases total where
    the statement prints one, otherwise that every line was read), so a bad parse is reported
    and skipped rather than half-imported. The PDF and its password are used for this request
    only; neither is stored."""
    # Not using the `Depends(get_db_dep)` pattern here: FastAPI runs a sync dependency for an
    # `async def` route in a different thread than the route body, and sqlite3 connections are
    # tied to the thread that created them, so a connection from the dependency would fail when
    # closed here. Opened and closed by hand instead, same as `refresh_and_snapshot`.
    if use_llm and not cards.llm_available():
        raise HTTPException(status_code=400, detail="The Claude fallback is not available: set ANTHROPIC_API_KEY and restart the backend")
    loaded = []
    for f in files:
        data = await f.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(status_code=400, detail=f"{f.filename} is too large to be a statement")
        loaded.append((f.filename or "statement.pdf", io.BytesIO(data)))
    db = get_db()
    try:
        # Each statement names its own card (and creates it the first time), so files from
        # different cards can be uploaded together. `card_id` is only an explicit override.
        return {"files": cards.import_files(db, card_id, loaded, password, use_llm)}
    finally:
        db.close()


@router.post("/cards/merchant-rule")
def cards_merchant_rule(data: MerchantRule, db=Depends(get_db_dep), session=Depends(get_session)):
    """Correct a merchant's cashback class. The correction is saved and re-applied to history."""
    if not data.pattern.strip():
        raise HTTPException(status_code=400, detail="A pattern is required")
    try:
        card = cards.get_card(db, data.card_id)
        if not card:
            raise HTTPException(status_code=400, detail="No card set up yet")
        valid = {c for c, _ in cards.profile_of(card)["classes"]}
        if data.cls not in valid:
            raise HTTPException(status_code=400, detail=f"Class must be one of: {', '.join(sorted(valid))}")
        # A correction replaces any earlier one for the same merchant: stacking them left conflicting rules behind
        # (three clicks through the dropdown made three rules, and only the newest counted).
        pattern = data.pattern.strip().upper()
        ids = [c["id"] for c in cards.family_of(db, card["id"])]
        session.query(CardMerchantRule).filter(
            CardMerchantRule.pattern == pattern, CardMerchantRule.match_type == data.match_type,
            CardMerchantRule.card_id.in_(ids)).delete(synchronize_session=False)
        session.add(CardMerchantRule(card_id=card["id"], pattern=pattern, match_type=data.match_type, cls=data.cls))
        session.commit()
        cards.reclassify_card(db, card["id"])
        return {"ok": True}
    finally:
        db.close()


@router.get("/cards/merchant-rules")
def cards_merchant_rules(card_id: int | None = None, db=Depends(get_db_dep), session=Depends(get_session)):
    try:
        card = cards.get_card(db, card_id)
        if not card:
            return []
        rules = session.query(CardMerchantRule).filter(
            (CardMerchantRule.card_id.is_(None)) | (CardMerchantRule.card_id == card["id"])
        ).order_by(CardMerchantRule.id.desc()).all()
        return [row_dict(r) for r in rules]
    finally:
        db.close()


@router.delete("/cards/merchant-rules/{rid}")
def cards_delete_merchant_rule(rid: int, db=Depends(get_db_dep), session=Depends(get_session)):
    try:
        rule = session.get(CardMerchantRule, rid)
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")
        card_id = rule.card_id
        session.delete(rule)
        session.commit()
        card = cards.get_card(db, card_id)
        if card:
            cards.reclassify_card(db, card["id"])
        return {"ok": True}
    finally:
        db.close()


class CardPatch(BaseModel):
    """Any subset of a card's details; what is left out is left alone."""
    name: str | None = None
    status: str | None = None          # active / closed
    issuer: str | None = None
    last4: str | None = None
    network: str | None = None
    notes: str | None = None
    profile: str | None = None         # reward scheme
    credit_limit: float | None = None
    annual_fee: float | None = None
    fee_waiver_spend: float | None = None
    statement_day: int | None = None
    grace_days: int | None = None
    color: str | None = None           # '#rrggbb'; '' returns it to an automatic colour


class CardCreate(BaseModel):
    name: str
    profile: str = "generic"
    last4: str = ""
    issuer: str = ""


@router.post("/cards")
def cards_create(data: CardCreate, db=Depends(get_db_dep)):
    """Add a card by hand; it appears on the Cards page straight away."""
    try:
        try:
            return cards.create_card(db, data.name, data.profile, data.last4, data.issuer)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()


class PerkIn(BaseModel):
    kind: str | None = None
    title: str | None = None
    detail: str | None = None
    value_yr: float | None = None
    source: str | None = None
    checked: bool | None = None


def _perk_call(fn, *args):
    import card_perks
    db = get_db()
    try:
        try:
            return getattr(card_perks, fn)(db, *args)
        except KeyError:
            raise HTTPException(status_code=404, detail="Not found")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()


@router.get("/cards/{cid}/perks")
def card_perks_list(cid: int):
    """A card's benefits, as written down (seeded from its scheme's published terms, marked to check)."""
    return _perk_call("list_perks", cid)


@router.post("/cards/{cid}/perks")
def card_perks_add(cid: int, data: PerkIn):
    return _perk_call("add_perk", cid, data.model_dump(exclude_none=True))


@router.patch("/cards/perks/{pid}")
def card_perks_update(pid: int, data: PerkIn):
    return _perk_call("update_perk", pid, data.model_dump(exclude_none=True))


@router.delete("/cards/perks/{pid}")
def card_perks_delete(pid: int):
    return _perk_call("delete_perk", pid)


@router.get("/cards/advice")
def cards_advice(db=Depends(get_db_dep)):
    """Which card to use for each kind of spend, and what the wrong card cost over the last 12 months."""
    import card_advisor
    try:
        return card_advisor.advice(db)
    finally:
        db.close()


@router.get("/cards/admin")
def cards_admin(db=Depends(get_db_dep)):
    """Every card for the admin page, closed ones included and listed last."""
    try:
        return cards.admin_list(db)
    finally:
        db.close()


class CardOrder(BaseModel):
    ids: list[int]


@router.put("/cards/order")
def cards_order(data: CardOrder, db=Depends(get_db_dep)):
    """Save the order cards were dragged into on the Cards page. Closed cards are placed like any other."""
    try:
        try:
            return {"ids": cards.set_card_order(db, data.ids)}
        except KeyError:
            raise HTTPException(status_code=404, detail="Card not found")
    finally:
        db.close()


@router.patch("/cards/{cid}")
def cards_patch(cid: int, data: CardPatch, db=Depends(get_db_dep)):
    """Rename a card, or mark it closed (redundant) or active again. A card is never deleted: closing keeps
    all its data and only greys it out."""
    try:
        try:
            return cards.update_card(db, cid, **data.model_dump())
        except KeyError:
            raise HTTPException(status_code=404, detail="Card not found")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()


@router.put("/cards/{cid}")
def cards_update(cid: int, data: CardSettings, db=Depends(get_db_dep), session=Depends(get_session)):
    """Edit a card. The name, reward scheme and rates apply to every number the card has had; the
    billing cycle applies to every card on the same bill, because they share one due date. Saving
    the cycle marks it verified: it means you have checked it against a statement."""
    try:
        card = cards.get_card(db, cid)
        if not card:
            raise HTTPException(status_code=404, detail="Card not found")
        profile = data.profile or card["profile"]
        if profile not in cards.PROFILES:
            raise HTTPException(status_code=400, detail="Unknown reward scheme")
        changed = profile != card["profile"]
        valid = {c for c, _ in cards.PROFILES[profile]["classes"]}
        rates = ({**cards.PROFILES[profile]["rates"], **{k: v for k, v in data.rates.items() if k in valid}}
                 if changed else {**cards.card_rates(card), **data.rates})
        if set(rates) - valid or any(not 0 <= v <= 100 for v in rates.values()):
            raise HTTPException(status_code=400, detail="Rates must be 0-100% and only for this card's reward classes")
        if not 1 <= data.statement_day <= 31:
            raise HTTPException(status_code=400, detail="Statement day must be between 1 and 31")
        if not 1 <= data.grace_days <= 60:
            raise HTTPException(status_code=400, detail="Days to the due date must be between 1 and 60")
        if not 0 <= data.pay_buffer_days <= data.grace_days - 1:
            raise HTTPException(status_code=400, detail="The safety margin must be shorter than the gap to the due date")
        if not 0 <= data.float_rate <= 30:
            raise HTTPException(status_code=400, detail="Rate must be between 0 and 30% a year")
        name = (data.name or "").strip()
        family = [c["id"] for c in cards.family_of(db, cid)]
        session.query(Card).filter(Card.id.in_(family)).update({
            "credit_limit": data.credit_limit, "annual_fee": data.annual_fee,
            "fee_waiver_spend": data.fee_waiver_spend, "cashback_cap": data.cashback_cap,
            "rates": json.dumps(rates), "profile": profile,
        }, synchronize_session=False)
        if name:
            session.query(Card).filter(Card.id == cid).update({"name": name}, synchronize_session=False)
        account_ids = [c["id"] for c in cards.account_cards(db, card["account_id"])]   # one bill, one cycle
        session.query(Card).filter(Card.id.in_(account_ids)).update({
            "statement_day": data.statement_day, "grace_days": data.grace_days,
            "pay_buffer_days": data.pay_buffer_days, "float_rate": data.float_rate, "cycle_verified": 1,
        }, synchronize_session=False)
        session.commit()
        cards.reclassify_card(db, cid)
        return {"ok": True}
    finally:
        db.close()


