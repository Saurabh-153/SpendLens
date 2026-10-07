"""A card's benefits, written down: what it pays, what it costs, what it excludes, what comes with it.

Each card has a list of entries (kind, title, detail, an optional yearly rupee value, where it came from, and
whether you have checked it against the card's own terms). A card starts from its scheme's published terms below, every
entry marked "to check", because issuers change terms and I have only the published ones; after that the list is
yours: edit it, add to it, tick entries off. Nothing here changes a reward computation.

An entry belongs to a physical card: it is stored on one of its numbers and read across all of them.
"""
from datetime import date

import cards as C

KINDS = [("rewards", "Rewards"), ("milestone", "Milestones and bonuses"), ("lounge", "Lounge and travel"), ("fees", "Fees"),
         ("exclusions", "Exclusions and caps"), ("insurance", "Insurance and protection"), ("other", "Other")]
KIND_IDS = [k for k, _ in KINDS]


def _p(kind, title, detail="", value=0, source="Built-in terms, not verified against your card"):
    return {"kind": kind, "title": title, "detail": detail, "value_yr": value, "source": source}


#: scheme -> starting entries. Only terms stated by the issuer or measured from your statements; nothing guessed.
SEEDS = {
    "sbi_cashback": [
        _p("rewards", "5% cashback on online spend", "Any online merchant, including Amazon, Flipkart, Swiggy, Zomato."),
        _p("rewards", "1% cashback on in-person spend", "Shops and other card-present spend."),
        _p("exclusions", "Some spend earns nothing", "Utilities, fuel, rent, wallet loads and similar are excluded from cashback. Confirm the current list on SBI Card's site."),
        _p("exclusions", "Monthly cashback cap", "A cap per statement may apply. Not confirmed from your statements: check and note it here."),
        _p("fees", "Annual fee Rs 999", "Waived when yearly spend reaches Rs 2 lakh."),
    ],
    "icici_amazon": [
        _p("rewards", "5% back on Amazon with Prime, 3% without", "Paid as Amazon Pay balance."),
        _p("rewards", "2% back on Amazon Pay partner merchants", "Only when paid through Amazon Pay."),
        _p("rewards", "1% back on everything else"),
        _p("fees", "Lifetime free", "No joining or annual fee.", source="You told me all your ICICI cards are lifetime free"),
        _p("exclusions", "Fuel earns no rewards", "Check the current exclusions on ICICI's site."),
    ],
    "icici_rubyx": [
        _p("rewards", "Base rate about 0.5%", "Reward points at about Rs 0.25 each. Check the exact earn rate and write it here.", source="Assumption used by the recommender, not verified"),
        _p("milestone", "3,000 bonus points at Rs 3 lakh a year", "1,500 more for each further lakh, up to 15,000 points.", 750),
        _p("lounge", "Domestic airport lounge: 2 visits a quarter", "After Rs 75,000 spend in the previous quarter."),
        _p("lounge", "8 railway lounge visits a year"),
        _p("fees", "Lifetime free", "No joining or annual fee.", source="You told me all your ICICI cards are lifetime free"),
    ],
    "icici_sapphiro": [
        _p("rewards", "Base rate about 0.5%", "Reward points at about Rs 0.25 each. Check the exact earn rate and write it here.", source="Assumption used by the recommender, not verified"),
        _p("milestone", "4,000 bonus points at Rs 4 lakh a year", "2,000 more for each further lakh, up to 20,000 points.", 1000),
        _p("lounge", "Domestic airport lounge: 4 visits a quarter", "After Rs 75,000 spend in that quarter."),
        _p("lounge", "2 international lounge visits a year", "Through Priority Pass."),
        _p("fees", "Lifetime free", "No joining or annual fee.", source="You told me all your ICICI cards are lifetime free"),
    ],
    "bob_eterna": [
        _p("rewards", "15 reward points per Rs 100 on online, travel and dining spend", "Worth about Rs 0.25 a point, so about 3.75%."),
        _p("rewards", "3 reward points per Rs 100 elsewhere", "About 0.75%."),
        _p("rewards", "Points are shown on every statement", "Your statements print points earned and the balance; the app reads them.", source="Measured from your statements"),
        _p("exclusions", "Fuel and some categories earn nothing", "Confirm the current list on the bank's site."),
    ],
    "hdfc_neu": [
        _p("rewards", "1.5% back as NeuCoins on most spend", "1 NeuCoin = Rs 1 on Tata Neu."),
        _p("rewards", "5% back on Tata brands", "BigBasket, Tata 1mg, Croma, Westside and others on the Tata Neu app or site.", source="Measured on your BigBasket purchases"),
        _p("exclusions", "Fuel, utilities and insurance may be capped or excluded", "Confirm the current list on HDFC's site."),
        _p("other", "UPI spend on the card earns the base NeuCoins", source="Measured from your statements"),
    ],
    "amex_smartearn": [
        _p("rewards", "10X points at partners", "Zomato, Ajio, Nykaa, BookMyShow, Uber and others: 10 points per Rs 50.", source="American Express India, as read in 2026"),
        _p("rewards", "5X points on Amazon", "5 points per Rs 50.", source="American Express India, as read in 2026"),
        _p("rewards", "1 point per Rs 50 elsewhere", "About 0.5% at Rs 0.25 a point (Amex does not state a value).", source="American Express India, as read in 2026"),
        _p("milestone", "Amazon vouchers of Rs 500 at Rs 1.2, 1.8 and 2.4 lakh a year", "Three vouchers in a membership year.", 1500, "American Express India, as read in 2026"),
        _p("fees", "Annual fee Rs 495, waived at Rs 40,000 a year", source="American Express India, as read in 2026"),
        _p("exclusions", "No points on fuel, insurance, utilities, cash or EMI conversion", source="American Express India, as read in 2026"),
        _p("other", "Closed to new applications", "American Express paused new SmartEarn applications in March 2025.", source="American Express India, as read in 2026"),
    ],
}


def _members(db, card_id):
    return [c["id"] for c in C.family_of(db, card_id)]


def _seed(db, card_id):
    """Start a card's list from its scheme, once. Never again, so deleting an entry stays deleted."""
    card = C.get_card(db, card_id)
    fam = _members(db, card_id)
    if any(C.get_card(db, i).get("perks_seeded") for i in fam):
        return
    for n, p in enumerate(SEEDS.get(card["profile"], [])):
        db.execute("INSERT INTO card_perks (card_id, kind, title, detail, value_yr, source, checked, sort) VALUES (?,?,?,?,?,?,0,?)",
                   (card_id, p["kind"], p["title"], p["detail"], p["value_yr"], p["source"], n))
    for i in fam:
        db.execute("UPDATE cards SET perks_seeded=1 WHERE id=?", (i,))
    db.commit()


def list_perks(db, card_id):
    """The card's entries, grouped by kind in a fixed order."""
    _seed(db, card_id)
    fam = _members(db, card_id)
    q = ",".join("?" * len(fam))
    rows = [dict(r) for r in db.execute(f"SELECT * FROM card_perks WHERE card_id IN ({q}) ORDER BY sort, id", fam)]
    for r in rows:
        r["checked"] = bool(r["checked"])
    return {"kinds": [{"id": k, "label": l} for k, l in KINDS], "perks": rows,
            "to_check": sum(1 for r in rows if not r["checked"]), "value_yr": round(sum(r["value_yr"] or 0 for r in rows), 2)}


def _clean(data, partial):
    out = {}
    if "kind" in data:
        if data["kind"] not in KIND_IDS:
            raise ValueError("Unknown kind of benefit")
        out["kind"] = data["kind"]
    if "title" in data:
        t = " ".join((data["title"] or "").split())
        if not t or len(t) > 120:
            raise ValueError("A benefit needs a title of 1 to 120 characters")
        out["title"] = t
    if "detail" in data:
        out["detail"] = (data["detail"] or "").strip()[:600]
    if "source" in data:
        out["source"] = (data["source"] or "").strip()[:160]
    if "value_yr" in data:
        v = data["value_yr"] or 0
        if not 0 <= v <= 1e7:
            raise ValueError("The yearly value must be a rupee amount, 0 or more")
        out["value_yr"] = float(v)
    if "checked" in data:
        out["checked"] = 1 if data["checked"] else 0
    if not partial and "title" not in out:
        raise ValueError("A benefit needs a title")
    return out


def add_perk(db, card_id, data):
    if not C.get_card(db, card_id):
        raise KeyError("card")
    _seed(db, card_id)
    f = _clean({"kind": "other", "detail": "", "source": "Added by you", "value_yr": 0, **data, "checked": data.get("checked", True)}, partial=False)
    top = db.execute("SELECT COALESCE(MAX(sort), -1) + 1 FROM card_perks WHERE card_id IN (%s)" % ",".join("?" * len(_members(db, card_id))),
                     _members(db, card_id)).fetchone()[0]
    db.execute("INSERT INTO card_perks (card_id, kind, title, detail, value_yr, source, checked, sort) VALUES (?,?,?,?,?,?,?,?)",
               (card_id, f["kind"], f["title"], f["detail"], f["value_yr"], f["source"], f["checked"], top))
    db.commit()
    return list_perks(db, card_id)


def update_perk(db, perk_id, data):
    row = db.execute("SELECT * FROM card_perks WHERE id=?", (perk_id,)).fetchone()
    if not row:
        raise KeyError("perk")
    f = _clean(data, partial=True)
    if f:
        # Rewording an entry yourself counts as checking it, unless the same request says otherwise.
        if "checked" not in f and any(k in f for k in ("title", "detail", "value_yr", "kind")):
            f["checked"] = 1                      # you wrote it yourself, so it is yours
        db.execute("UPDATE card_perks SET " + ", ".join(f"{k}=?" for k in f) + ", updated=? WHERE id=?",
                   (*f.values(), date.today().isoformat(), perk_id))
        db.commit()
    return list_perks(db, row["card_id"])


def delete_perk(db, perk_id):
    row = db.execute("SELECT card_id FROM card_perks WHERE id=?", (perk_id,)).fetchone()
    if not row:
        raise KeyError("perk")
    db.execute("DELETE FROM card_perks WHERE id=?", (perk_id,))
    db.commit()
    return list_perks(db, row["card_id"])
