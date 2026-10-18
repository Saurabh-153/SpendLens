import io
import json
import cards
from pydantic import BaseModel
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from ._common import row_dict
from db.engine import SessionLocal, get_session
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
def cards_list(session=Depends(get_session)):
    """One entry per physical card, most recently used first. A card that was re-issued under a
    new number is one entry listing all its numbers."""
    return cards.list_cards(session)


@router.get("/cards/overview")
def cards_overview(session=Depends(get_session)):
    """Usage across every card: spend, cost, what is due next, and spend by financial year."""
    return cards.overview(session)


@router.get("/cards/dashboard")
def cards_dashboard(card_id: int | None = None, session=Depends(get_session)):
    """Spend, cashback earned vs computed, merchant breakdown, leakage and fee progress."""
    return cards.dashboard(session, card_id)


@router.get("/cards/transactions")
def cards_transactions(card_id: int | None = None, limit: int = Query(500, le=5000), session=Depends(get_session)):
    card = cards.get_card(session, card_id)
    if not card:
        return []
    return [dict(r) for r in cards.query(
        session, """SELECT t.*, s.period_to FROM card_txns t
                    LEFT JOIN card_statements s ON s.id = t.statement_id
                    WHERE t.card_id=:card_id ORDER BY t.tx_date DESC, t.id DESC LIMIT :limit""",
        card_id=card["id"], limit=limit).mappings()]


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
    if use_llm and not cards.llm_available():
        raise HTTPException(status_code=400, detail="The Claude fallback is not available: set ANTHROPIC_API_KEY and restart the backend")
    loaded = []
    for f in files:
        data = await f.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(status_code=400, detail=f"{f.filename} is too large to be a statement")
        loaded.append((f.filename or "statement.pdf", io.BytesIO(data)))
    with SessionLocal() as session:
        # Each statement names its own card (and creates it the first time), so files from
        # different cards can be uploaded together. `card_id` is only an explicit override.
        return {"files": cards.import_files(session, card_id, loaded, password, use_llm)}


@router.post("/cards/merchant-rule")
def cards_merchant_rule(data: MerchantRule, session=Depends(get_session)):
    """Correct a merchant's cashback class. The correction is saved and re-applied to history."""
    if not data.pattern.strip():
        raise HTTPException(status_code=400, detail="A pattern is required")
    card = cards.get_card(session, data.card_id)
    if not card:
        raise HTTPException(status_code=400, detail="No card set up yet")
    valid = {c for c, _ in cards.profile_of(card)["classes"]}
    if data.cls not in valid:
        raise HTTPException(status_code=400, detail=f"Class must be one of: {', '.join(sorted(valid))}")
    # A correction replaces any earlier one for the same merchant: stacking them left conflicting rules behind
    # (three clicks through the dropdown made three rules, and only the newest counted).
    pattern = data.pattern.strip().upper()
    ids = [c["id"] for c in cards.family_of(session, card["id"])]
    session.query(CardMerchantRule).filter(
        CardMerchantRule.pattern == pattern, CardMerchantRule.match_type == data.match_type,
        CardMerchantRule.card_id.in_(ids)).delete(synchronize_session=False)
    session.add(CardMerchantRule(card_id=card["id"], pattern=pattern, match_type=data.match_type, cls=data.cls))
    session.commit()
    cards.reclassify_card(session, card["id"])
    return {"ok": True}


@router.get("/cards/merchant-rules")
def cards_merchant_rules(card_id: int | None = None, session=Depends(get_session)):
    card = cards.get_card(session, card_id)
    if not card:
        return []
    rules = session.query(CardMerchantRule).filter(
        (CardMerchantRule.card_id.is_(None)) | (CardMerchantRule.card_id == card["id"])
    ).order_by(CardMerchantRule.id.desc()).all()
    return [row_dict(r) for r in rules]


@router.delete("/cards/merchant-rules/{rid}")
def cards_delete_merchant_rule(rid: int, session=Depends(get_session)):
    rule = session.get(CardMerchantRule, rid)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    card_id = rule.card_id
    session.delete(rule)
    session.commit()
    card = cards.get_card(session, card_id)
    if card:
        cards.reclassify_card(session, card["id"])
    return {"ok": True}


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
def cards_create(data: CardCreate, session=Depends(get_session)):
    """Add a card by hand; it appears on the Cards page straight away."""
    try:
        return cards.create_card(session, data.name, data.profile, data.last4, data.issuer)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class PerkIn(BaseModel):
    kind: str | None = None
    title: str | None = None
    detail: str | None = None
    value_yr: float | None = None
    source: str | None = None
    checked: bool | None = None


def _perk_call(fn, *args):
    import card_perks
    with SessionLocal() as session:
        try:
            return getattr(card_perks, fn)(session, *args)
        except KeyError:
            raise HTTPException(status_code=404, detail="Not found")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))


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
def cards_advice(session=Depends(get_session)):
    """Which card to use for each kind of spend, and what the wrong card cost over the last 12 months."""
    import card_advisor
    return card_advisor.advice(session)


@router.get("/cards/admin")
def cards_admin(session=Depends(get_session)):
    """Every card for the admin page, closed ones included and listed last."""
    return cards.admin_list(session)


class CardOrder(BaseModel):
    ids: list[int]


@router.put("/cards/order")
def cards_order(data: CardOrder, session=Depends(get_session)):
    """Save the order cards were dragged into on the Cards page. Closed cards are placed like any other."""
    try:
        return {"ids": cards.set_card_order(session, data.ids)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Card not found")


@router.patch("/cards/{cid}")
def cards_patch(cid: int, data: CardPatch, session=Depends(get_session)):
    """Rename a card, or mark it closed (redundant) or active again. A card is never deleted: closing keeps
    all its data and only greys it out."""
    try:
        return cards.update_card(session, cid, **data.model_dump())
    except KeyError:
        raise HTTPException(status_code=404, detail="Card not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/cards/{cid}")
def cards_update(cid: int, data: CardSettings, session=Depends(get_session)):
    """Edit a card. The name, reward scheme and rates apply to every number the card has had; the
    billing cycle applies to every card on the same bill, because they share one due date. Saving
    the cycle marks it verified: it means you have checked it against a statement."""
    card = cards.get_card(session, cid)
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
    family = [c["id"] for c in cards.family_of(session, cid)]
    session.query(Card).filter(Card.id.in_(family)).update({
        "credit_limit": data.credit_limit, "annual_fee": data.annual_fee,
        "fee_waiver_spend": data.fee_waiver_spend, "cashback_cap": data.cashback_cap,
        "rates": json.dumps(rates), "profile": profile,
    }, synchronize_session=False)
    if name:
        session.query(Card).filter(Card.id == cid).update({"name": name}, synchronize_session=False)
    account_ids = [c["id"] for c in cards.account_cards(session, card["account_id"])]   # one bill, one cycle
    session.query(Card).filter(Card.id.in_(account_ids)).update({
        "statement_day": data.statement_day, "grace_days": data.grace_days,
        "pay_buffer_days": data.pay_buffer_days, "float_rate": data.float_rate, "cycle_verified": 1,
    }, synchronize_session=False)
    session.commit()
    cards.reclassify_card(session, cid)
    return {"ok": True}
