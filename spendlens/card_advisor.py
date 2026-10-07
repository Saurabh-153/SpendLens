"""Which card for what: the card to use for each kind of spend, and what not following it has cost.

How it works
------------
Every spend is given a *purpose* (Amazon, groceries, food delivery, utilities, fuel ...) from its merchant,
its description and, where the issuer gives one, its category. `TERMS` holds, for each reward scheme, what a
card pays on each purpose as a percent of spend, worked out in rupees (points x what a point is worth).
For a purpose the best card is the one that pays most; the runner-up is shown too. Closed cards are left out.

The same table prices history: for each spend in the last 12 months, what the card it was put on would have
paid, against what the best card would have paid. The difference is "left on the table".

What it can and cannot know
---------------------------
The rates are the issuers' published terms, not measured, and each carries how sure we are:

    published   stated by the issuer
    observed    measured from the user's own statements (BOB's UPI rate, HDFC's bonus on BigBasket)
    assumed     an inference or a value we had to pick: what a point is worth, whether an exclusion applies

Point values are the main assumption (BOB and Rubyx / Sapphiro / Amex points Rs 0.25, a NeuCoin Rs 1). Nothing
here sees monthly caps, milestone bonuses, lounge access or annual fees, so those appear as notes next to a
card, not in its rate. The ranking is by reward rate only: that is the thing that is easy to check.
"""
import re
from datetime import date, timedelta

#: id, label, what falls in it
PURPOSES = [
    ("amazon", "Amazon", "Amazon.in, Amazon Fresh"),
    ("tata", "Tata brands", "BigBasket, Tata 1mg, Croma, Westside"),
    ("quick", "Groceries and quick commerce", "Zepto, Blinkit, Instamart, DMart, Licious, supermarkets"),
    ("food", "Food delivery and dining", "Swiggy, Zomato, restaurants"),
    ("shopping", "Online shopping", "Flipkart, Myntra, Meesho, Nykaa, FirstCry"),
    ("travel", "Travel", "Trains, flights, hotels, cabs"),
    ("bills", "Utilities and telecom", "Electricity, mobile, broadband, DTH"),
    ("insurance", "Insurance premiums", "Life, health and motor policies"),
    ("fuel", "Fuel", "Petrol pumps"),
    ("health", "Health and pharmacy", "Hospitals, clinics, pharmacies"),
    ("upi", "UPI scan and pay", "Shops paid by UPI on a credit card"),
    ("instore", "In-store and everything else", "Anything not above"),
]
PURPOSE_IDS = [p[0] for p in PURPOSES]


def _t(rate, note="", conf="published"):
    return {"rate": float(rate), "note": note, "conf": conf}


def _flat(rate, **special):
    """A rate for every purpose, with exceptions by purpose id."""
    out = {p: _t(rate) for p in PURPOSE_IDS}
    for k, v in special.items():
        out[k] = v if isinstance(v, dict) else _t(v)
    return out


ICICI_PREMIUM = _flat(
    0.5, bills=_t(0.25, "1 point per Rs 100"), insurance=_t(0.25, "1 point per Rs 100"), fuel=_t(0, "no points on fuel"),
    upi=_t(0, "a Visa/Mastercard cannot pay by UPI", "assumed"))

#: scheme (cards.PROFILES key) -> {purpose: {rate, note, conf}}. Rates are percent of spend in rupees.
TERMS = {
    "sbi_cashback": {
        **_flat(1.0, amazon=_t(5, "any online spend earns 5%"), tata=_t(5, "online"), quick=_t(5, "online; 1% in a shop"),
                food=_t(5, "online"), shopping=_t(5, "online"), travel=_t(5, "online; railways are excluded", "assumed"),
                bills=_t(0, "utilities are excluded"), insurance=_t(0, "treated as excluded; not confirmed", "assumed"),
                fuel=_t(0, "fuel is excluded"), health=_t(1, "a shop or hospital pays 1%; an online pharmacy would pay 5%"),
                upi=_t(0, "a Visa cannot pay by UPI", "assumed"), instore=_t(1, "in person pays 1%")),
    },
    "icici_amazon": _flat(
        1.0, amazon=_t(5, "5% with Prime, 3% without"), food=_t(2, "an Amazon Pay partner, if paid through Amazon Pay", "assumed"),
        bills=_t(2, "2% only when paid through Amazon Pay", "assumed"), fuel=_t(0, "fuel is excluded"),
        upi=_t(0, "a Visa cannot pay by UPI", "assumed")),
    "icici_rubyx": ICICI_PREMIUM,
    "icici_sapphiro": ICICI_PREMIUM,
    "bob_eterna": _flat(
        0.75, amazon=_t(3.75, "15 points per Rs 100 online, at Rs 0.25", "published"), tata=_t(3.75, "online"), quick=_t(3.75, "online"),
        food=_t(3.75, "dining and online"), shopping=_t(3.75, "online"), travel=_t(3.75, "travel pays 15 points per Rs 100"),
        fuel=_t(0, "fuel earns nothing here", "assumed"), upi=_t(0.83, "measured on your statements: about 3.3 points per Rs 100", "observed"),
        instore=_t(0.75, "3 points per Rs 100")),
    "hdfc_neu": _flat(
        1.5, tata=_t(5, "1.5% base plus 3.5% on Tata brands, measured on your BigBasket purchases", "observed"),
        bills=_t(1.5, "base NeuCoins; utilities and insurance may be capped", "assumed"), insurance=_t(1.5, "may be capped", "assumed"),
        fuel=_t(0, "fuel is excluded", "assumed"), upi=_t(1.5, "UPI is eligible for base NeuCoins", "observed")),
    "amex_smartearn": _flat(
        0.5, amazon=_t(2.5, "5X points per Rs 50", "assumed"), food=_t(0.5, "10X only at partners: Zomato (see exceptions)", "assumed"),
        bills=_t(0, "utilities are excluded"), insurance=_t(0, "insurance is excluded"), fuel=_t(0, "fuel is excluded"),
        upi=_t(0, "not a UPI card", "assumed")),
}
# Where a card pays far more at one named merchant than its purpose rate: merchant -> rate. These are shown as
# exceptions and used when pricing history.
OVERRIDES = {
    "amex_smartearn": {"zomato": 5.0, "uber": 5.0, "nykaa": 5.0, "ajio": 5.0, "bookmyshow": 5.0},
}
#: what a point is worth, per scheme: the assumption behind the rates above (shown to the user)
POINT_VALUE = {
    "bob_eterna": "1 reward point = Rs 0.25", "icici_rubyx": "1 reward point = Rs 0.25", "icici_sapphiro": "1 reward point = Rs 0.25",
    "hdfc_neu": "1 NeuCoin = Rs 1", "amex_smartearn": "1 Membership Rewards point = Rs 0.25 (Amex does not state it)",
    "sbi_cashback": "cashback in rupees", "icici_amazon": "Amazon Pay balance in rupees",
}
NOTES = {
    "sbi_cashback": "Annual fee Rs 999, waived at Rs 2L a year. The monthly cashback cap is not confirmed.",
    "icici_amazon": "Lifetime free. Needs Prime for 5% on Amazon.",
    "icici_rubyx": "Worth keeping for the yearly milestone (3,000 points at Rs 3L) and lounge visits, not for everyday rates.",
    "icici_sapphiro": "Worth keeping for the yearly milestone (4,000 points at Rs 4L) and lounge visits, not for everyday rates.",
    "bob_eterna": "The only card here that pays 15 points per Rs 100 on dining, travel and online spend, and one of two that take UPI.",
    "hdfc_neu": "Pays 5% on Tata brands; also takes UPI. NeuCoins move to Tata Neu by themselves.",
    "amex_smartearn": "Annual fee Rs 495, waived at Rs 40,000. Amex stopped taking new SmartEarn applications in March 2025.",
}

# ------------------------------------------------------------------ what a spend was for

_RULES = [
    ("amazon", ("AMAZON", "ASSPL")),
    ("tata", ("BIGBASKET", "BIG BASKET", "INNOVATIVE RETAIL", "1MG", "CROMA", "WESTSIDE", "TATA CLIQ", "TATA DIGITAL", "TATAPLAY")),
    ("fuel", ("HPCL", "BPCL", "IOCL", "INDIAN OIL", "PETROL", "FUEL", "SHELL", "BHARAT PETRO")),
    ("insurance", ("INSUR", "MAX LIFE", "HDFC LIFE", "POLICYBAZAAR", "LIC OF INDIA", "ACKO", "STAR HEALTH", "ERGO")),
    ("bills", ("AIRTEL", "JIO", "VODAFONE", "BSNL", "TATA PLAY", "BROADBAND", "ELECTRIC", "BESCOM", "WBSEDCL", "FIBER", "HATHWAY", "RECHARGE", "DTH", "WATER BILL")),
    ("travel", ("IXIGO", "YATRA", "MAKEMYTRIP", "IRCTC", "UBER", "OLA ", "RAPIDO", "REDBUS", "GOIBIBO", "INDIGO", "AIR INDIA", "AKASA", "HOTEL", "OYO", "IBIBO", "DREAMFOLKS")),
    ("food", ("SWIGGY", "ZOMATO", "BUNDL", "ETERNAL", "DINING", "MC DONALD", "MCDONALD", "KFC", "DOMINO", "BURGER KING", "PIZZA", "CAFE", "RESTAURANT", "BISMILLAH")),
    ("quick", ("ZEPTO", "BLINKIT", "INSTAMART", "DMART", "AVENUE SUPERMARTS", "SPENCER", "RELIANCE FRESH", "LICIOUS", "DELIGHTFUL GOURMET", "SUPERMARKET", "MEGA MART", "TENDER CUTS", "MORE ")),
    ("health", ("PHARM", "APOLLO", "MEDPLUS", "NETMEDS", "HOSPITAL", "CLINIC", "DIAGNOSTIC", "HEALTH", "DENTAL", "SMILE", "OPTIVAL", "PEDIAPULSE", "LABS", "BNWCCC")),
    ("shopping", ("FLIPKART", "MYNTRA", "MEESHO", "NYKAA", "AJIO", "FIRSTCRY", "LIFESTYLE", "FASHNEAR", "TRENT", "LIFE STYLE", "IKEA", "DECATHLON")),
]
_CATEGORY = [("INSURANCE", "insurance"), ("UTILIT", "bills"), ("COMMUNICATION", "bills"), ("GOVERNMENT", "bills"), ("TRAVEL", "travel"),
             ("HEALTH", "health"), ("RESTAURANT", "food"), ("GROCER", "quick")]


def purpose_of(merchant, detail="", category=""):
    """The purpose of one spend. A UPI payment is its own purpose: only some cards can make it."""
    d, m, c = (detail or "").upper(), (merchant or "").upper(), (category or "").upper()
    if d.startswith("UPI-"):
        return "upi"
    text = f"{m} {d}"
    for pid, words in _RULES:
        if any(w in text for w in words):
            return pid
    for key, pid in _CATEGORY:
        if key in c:
            return pid
    return "instore"


def rate_for(profile, purpose, alias_name=""):
    """What a scheme pays, in percent, on a purpose (a named merchant can beat it). None if the scheme is unknown."""
    t = TERMS.get(profile)
    if t is None:
        return None
    base = t.get(purpose, t["instore"])["rate"]
    return max(base, OVERRIDES.get(profile, {}).get((alias_name or "").lower(), 0.0))


# ------------------------------------------------------------------ the advice

def rank(cards_, purpose):
    """Cards ordered best first for a purpose: [(card, rate, term)]. `cards_` carry id, name, profile."""
    rows = [(c, TERMS[c["profile"]][purpose]["rate"], TERMS[c["profile"]][purpose]) for c in cards_ if c["profile"] in TERMS]
    return sorted(rows, key=lambda r: (-r[1], r[0]["id"]))


def advice(db, today=None):
    """Per purpose, the best and next-best card, the user's spend and what the wrong card cost, over 12 months."""
    import cards as C
    today = today or date.today()
    all_cards = C.list_cards(db)
    active = [c for c in all_cards if (c["status"] or "active") != "closed" and c["profile"] in TERMS]
    since = (today - timedelta(days=365)).isoformat()
    member_card = {m: c for c in all_cards for m in c["members"]}
    q = ",".join("?" * len(member_card)) or "NULL"
    rows = db.execute(f"""SELECT card_id, tx_date, merchant, detail, category, amount, is_spend, kind FROM card_txns
                          WHERE card_id IN ({q}) AND tx_date >= ? AND (is_spend=1 OR kind='refund')""",
                      (*member_card, since)).fetchall()

    spend, missed, earned, best_pot = ({p: 0.0 for p in PURPOSE_IDS} for _ in range(4))
    exceptions = {}
    for r in rows:
        card = member_card[r["card_id"]]
        if card["profile"] not in TERMS:
            continue
        net = r["amount"] if r["is_spend"] else -r["amount"]
        alias = C.alias(r["merchant"])
        p = purpose_of(alias, r["detail"], r["category"])
        actual = rate_for(card["profile"], p, alias)
        best = max((rate_for(c["profile"], p, alias) for c in active), default=0.0)
        spend[p] += net
        earned[p] += net * actual / 100
        best_pot[p] += net * best / 100
        missed[p] += net * max(best - actual, 0) / 100
        for c in active:                                             # a named merchant that beats the purpose's best
            specific = rate_for(c["profile"], p, alias)
            if specific > TERMS[c["profile"]][p]["rate"] and specific >= best and alias:
                exceptions[(alias, c["id"])] = {"merchant": alias, "card_id": c["id"], "card": c["name"], "rate": specific, "purpose": p}

    out = []
    for pid, label, examples in PURPOSES:
        ranked = rank(active, pid)
        top = ranked[0] if ranked else None
        nxt = next((r for r in ranked[1:] if r[1] < top[1]), None) if top else None
        tied = [r[0]["name"] for r in ranked if top and r[1] == top[1]]
        out.append({
            "id": pid, "label": label, "examples": examples,
            "best": {"card_id": top[0]["id"], "color": top[0]["color"], "name": top[0]["name"], "profile": top[0]["profile"], "rate": top[1], "note": top[2]["note"],
                     "conf": top[2]["conf"], "also": [n for n in tied if n != top[0]["name"]]} if top and top[1] > 0 else None,
            "next": {"card_id": nxt[0]["id"], "color": nxt[0]["color"], "name": nxt[0]["name"], "rate": nxt[1], "note": nxt[2]["note"]} if nxt and nxt[1] > 0 else None,
            "spend_12m": round(spend[pid], 2), "earned_12m": round(earned[pid], 2),
            "missed_12m": round(missed[pid], 2),
            "nothing_earns": not top or top[1] == 0,
        })
    # a card that is never the best at anything
    best_ids = {o["best"]["card_id"] for o in out if o["best"]}
    return {
        "today": today.isoformat(), "since": since,
        "purposes": out,
        "exceptions": sorted(exceptions.values(), key=lambda e: (e["merchant"], -e["rate"])),
        "cards": [{"id": c["id"], "color": c["color"], "name": c["name"], "profile": c["profile"], "scheme": C.PROFILE_LABELS.get(c["profile"], c["profile"]),
                   "best_for": [o["label"] for o in out if o["best"] and o["best"]["card_id"] == c["id"]],
                   "never_best": c["id"] not in best_ids, "value": POINT_VALUE.get(c["profile"], ""), "note": NOTES.get(c["profile"], "")}
                  for c in active],
        "closed": [c["name"] for c in all_cards if (c["status"] or "active") == "closed"],
        "totals": {"spend_12m": round(sum(spend.values()), 2), "earned_12m": round(sum(earned.values()), 2),
                   "best_12m": round(sum(best_pot.values()), 2), "missed_12m": round(sum(missed.values()), 2)},
        "assumptions": sorted({POINT_VALUE[c["profile"]] for c in active if c["profile"] in POINT_VALUE and "rupees" not in POINT_VALUE[c["profile"]]}),
    }
