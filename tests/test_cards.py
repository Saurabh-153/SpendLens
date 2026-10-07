"""Credit-card statement parsing and the cashback earn engine.

The tests that need real statements use the PDFs in `screenshot/` and are skipped when
they are not there or no password is given (set SPENDLENS_STMT_PASSWORD to run them).
Everything else runs on synthetic text, so the suite is useful without the private data.
"""
import glob
import os

import pytest

import cards
import database

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDFS = sorted(glob.glob(os.path.join(ROOT, "screenshot", "6801*.pdf")))  # the SBI Card statements
PASSWORD = os.environ.get("SPENDLENS_STMT_PASSWORD", "")

# A statement reduced to the parts the parser reads.
FAKE = """\
for Statement Period: 12 Aug 26 to 11 Sep 26
1,000.00
200.00
4,00,000.00
1,20,000.00
3,99,000.00
1,20,000.00
500.00
1,350.00
0.00
11 Sep 2026
01 Oct 2026
TRANSACTIONS FOR TEST
11 Aug 26 PAYMENT RECEIVED 000X 500.00 C
12 Aug 26 PYU*FLIPKART INTERNET  Bangalore     IND 1,000.00 D
13 Aug 26 COMPASS INDIA FOOD S   aRoadSector   IND 250.00 D
14 Aug 26 HPCL PETROL PUMP       Bangalore     IND 100.00 D
statement Date. T&C Apply
51
"""


def test_parses_period_dates_and_transactions():
    p = cards.parse_statement(FAKE)
    assert p["period_from"] == "2026-08-12" and p["period_to"] == "2026-09-11"
    assert p["stmt_date"] == "2026-09-11" and p["due_date"] == "2026-10-01"
    assert p["purchases"] == 1350.0 and p["credit_limit"] == 400000.0
    assert p["cashback_reported"] == 51
    assert len(p["txns"]) == 4
    assert sum(t["is_spend"] for t in p["txns"]) == 3, "the payment is not spend"


def test_parse_is_rejected_when_totals_disagree():
    """A partial parse must fail loudly rather than import a wrong statement."""
    bad = FAKE.replace("1,350.00", "9,999.00")
    with pytest.raises(ValueError, match="refusing to import"):
        cards.parse_statement(bad)


def test_not_a_statement_is_rejected():
    with pytest.raises(ValueError, match="statement period"):
        cards.parse_statement("some other pdf entirely")


def test_split_detail_separates_merchant_city_and_emi():
    m, city, emi = cards.split_detail("AMAZON PAY INDIA PRIVA  Bangalore     IND (Pay in EMIs)")
    assert m == "AMAZON PAY INDIA PRIVA" and city == "Bangalore" and emi is True
    m, _, emi = cards.split_detail("ZOMATO                 NEW DELHI     IND")
    assert m == "ZOMATO" and emi is False


@pytest.mark.parametrize("merchant,expected", [
    ("PYU*FLIPKART INTERNET", "online"),   # a payment aggregator means a web checkout
    ("WWWBIGBASKETCOM", "online"),
    ("AMAZON PAY INDIA PRIVA", "online"),
    ("COMPASS INDIA FOOD S", "offline"),   # nothing says online, so assume a swipe
    ("HPCL PETROL PUMP", "excluded"),      # fuel earns nothing
    ("TATA PLAY BROADBAND PV", "excluded"),  # a utility earns nothing
    ("IND*AMAZON - IRCTC", "excluded"),    # railways outrank being online
])
def test_classification(merchant, expected):
    assert cards.classify(merchant) == expected


def test_exclusions_win_over_online():
    """Rule order matters: an excluded category must beat an online match."""
    assert cards.classify("PYU*HPCL FUEL") == "excluded"


def test_alias_groups_a_merchants_many_spellings():
    for raw in ("ASSPL", "AMAZON PAY INDIA PRIVA", "Amazon Seller Services", "WWW AMAZON IN"):
        assert cards.alias(raw) == "Amazon"
    assert cards.alias("BUNDL TECHNOLOGIES") == "Swiggy"


def test_earn_applies_the_right_rate_per_class():
    txns = [
        {"tx_date": "2026-08-12", "merchant": "PYU*FLIPKART", "amount": 1000.0, "is_spend": 1},
        {"tx_date": "2026-08-13", "merchant": "COMPASS INDIA", "amount": 1000.0, "is_spend": 1},
        {"tx_date": "2026-08-14", "merchant": "HPCL PETROL", "amount": 1000.0, "is_spend": 1},
    ]
    total = cards.earn(txns, cards.DEFAULT_RULES)
    assert total == 60.0, "5% + 1% + 0% of 1000 each"
    assert [t["cashback"] for t in txns] == [50.0, 10.0, 0.0]


def test_cap_stops_earning_and_is_marked():
    txns = [{"tx_date": f"2026-08-{d:02d}", "merchant": "PYU*SHOP", "amount": 50000.0, "is_spend": 1}
            for d in (12, 13, 14)]
    total = cards.earn(txns, cards.DEFAULT_RULES, cap=5000)
    assert total == 5000.0
    assert txns[0]["cashback"] == 2500.0 and txns[0]["capped"] == 0
    assert txns[2]["cashback"] == 0.0 and txns[2]["capped"] == 1


def test_earn_is_ordered_by_date_not_list_order():
    """Once the cap binds, an earlier spend is worth more - so order must be by date."""
    txns = [{"tx_date": "2026-08-20", "merchant": "PYU*LATE", "amount": 100000.0, "is_spend": 1},
            {"tx_date": "2026-08-01", "merchant": "PYU*EARLY", "amount": 100000.0, "is_spend": 1}]
    cards.earn(txns, cards.DEFAULT_RULES, cap=5000)
    early = next(t for t in txns if t["merchant"] == "PYU*EARLY")
    assert early["cashback"] == 5000.0, "the earlier transaction should earn first"


def test_a_user_rule_overrides_the_defaults(seeded_db):
    db = database.get_db()
    try:
        card = cards.get_card(db)
        assert card, "migration 4 should seed a card"
        assert cards.classify("COMPASS INDIA FOOD S", cards.user_rules(db, card["id"])) == "offline"
        db.execute("""INSERT INTO card_merchant_rules (card_id, pattern, match_type, cls)
                      VALUES (?, 'COMPASS INDIA', 'contains', 'excluded')""", (card["id"],))
        db.commit()
        assert cards.classify("COMPASS INDIA FOOD S", cards.user_rules(db, card["id"])) == "excluded"
        db.execute("DELETE FROM card_merchant_rules WHERE card_id=?", (card["id"],))
        db.commit()
    finally:
        db.close()


def test_dashboard_without_statements_is_empty_not_broken(seeded_db):
    db = database.get_db()
    try:
        d = cards.dashboard(db)
        assert d["card"] is not None
        assert d["totals"]["spend"] == 0 and d["months"] == []
    finally:
        db.close()


# --------------------------------------------------- against the real statements

needs_pdfs = pytest.mark.skipif(
    not PDFS or not PASSWORD,
    reason="needs screenshot/*.pdf and SPENDLENS_STMT_PASSWORD")


@needs_pdfs
def test_every_real_statement_parses_and_balances():
    for path in PDFS:
        p = cards.parse_statement(cards.read_pdf(path, PASSWORD))
        assert p["txns"], f"{os.path.basename(path)} had no transactions"
        assert p["cashback_reported"] is not None, f"{os.path.basename(path)} had no cashback figure"
        # parse_statement already raises if this does not hold; assert it plainly too
        assert abs(sum(t["amount"] for t in p["txns"] if t["is_spend"]) - p["purchases"]) <= 1


@needs_pdfs
def test_importing_twice_adds_no_rows(seeded_db, tmp_path):
    db = database.get_db()
    try:
        cid = cards.get_card(db)["id"]
        files = [(os.path.basename(p), p) for p in PDFS]
        first = cards.import_files(db, cid, files, PASSWORD)
        assert all(f["ok"] for f in first), [f for f in first if not f["ok"]]
        before = db.execute("SELECT COUNT(*) FROM card_txns").fetchone()[0]
        again = cards.import_files(db, cid, files, PASSWORD)
        assert all(f["added"] == 0 for f in again), "a second import must add nothing"
        assert db.execute("SELECT COUNT(*) FROM card_txns").fetchone()[0] == before
    finally:
        db.close()


@needs_pdfs
def test_computed_cashback_is_close_to_what_was_paid(seeded_db):
    """The rules are a model, not the truth; this pins how far off the model may drift."""
    db = database.get_db()
    try:
        cid = cards.get_card(db)["id"]
        cards.import_files(db, cid, [(os.path.basename(p), p) for p in PDFS], PASSWORD)
        d = cards.dashboard(db)
        paid, calc = d["totals"]["cashback_paid"], d["totals"]["cashback_calc"]
        assert paid > 0
        assert abs(calc - paid) / paid < 0.05, f"computed {calc} vs paid {paid} is over 5% out"
        for m in d["months"]:
            assert abs(m["calc"] - m["cashback"]) < 250, f"{m['period_to']} is far out"
    finally:
        db.close()


# --------------------------------------------------- upload, registry and the Claude fallback

API = "/spendlens/api"


def blank_pdf():
    import io
    import pypdf
    w = pypdf.PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def test_parsers_endpoint_lists_formats_and_llm_state(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    d = client.get(f"{API}/cards/parsers").json()
    assert d["formats"] == ["SBI Card", "ICICI Bank", "Bank of Baroda", "HDFC Bank", "American Express"] and d["llm_available"] is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert client.get(f"{API}/cards/parsers").json()["llm_available"] is True


def test_upload_reports_a_non_pdf_without_importing(client):
    r = client.post(f"{API}/cards/upload", files=[("files", ("notes.pdf", b"not a pdf", "application/pdf"))])
    assert r.status_code == 200
    f = r.json()["files"][0]
    assert f["ok"] is False and "not a readable PDF" in f["error"]


def test_upload_reports_a_pdf_with_no_text(client):
    r = client.post(f"{API}/cards/upload", files=[("files", ("scan.pdf", blank_pdf(), "application/pdf"))])
    assert "no text layer" in r.json()["files"][0]["error"]


def test_one_bad_file_does_not_stop_the_others(client):
    files = [("files", ("a.pdf", b"junk", "application/pdf")),
             ("files", ("b.pdf", blank_pdf(), "application/pdf"))]
    out = client.post(f"{API}/cards/upload", files=files).json()["files"]
    assert [f["file"] for f in out] == ["a.pdf", "b.pdf"] and not any(f["ok"] for f in out)


def test_llm_flag_without_a_key_is_refused_up_front(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post(f"{API}/cards/upload", data={"use_llm": "true"},
                    files=[("files", ("a.pdf", blank_pdf(), "application/pdf"))])
    assert r.status_code == 400 and "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_unrecognised_format_without_llm_says_what_to_do():
    with pytest.raises(ValueError, match="unrecognised statement format"):
        cards.parse_any("HDFC Bank Credit Card Statement ...")


def test_the_known_format_never_goes_near_claude(monkeypatch):
    def boom(_):
        raise AssertionError("Claude must not be called for a format we can read")
    monkeypatch.setattr(cards, "_llm_complete", boom)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    parsed, name = cards.parse_any("SBI Card\n" + FAKE, allow_llm=True)
    assert name == "SBI Card" and parsed[0]["purchases"] == 1350.0


GOOD_LLM = """{"period_from": "2026-08-12", "period_to": "2026-09-11", "stmt_date": "2026-09-11",
 "due_date": "2026-10-01", "total_due": 1000, "min_due": 200, "credit_limit": 400000,
 "available_credit": 399000, "credits": 500, "purchases": 1350, "fees": 0,
 "cashback_reported": 51,
 "txns": [{"tx_date": "2026-08-11", "detail": "PAYMENT RECEIVED 000X", "amount": 500, "dc": "C"},
          {"tx_date": "2026-08-12", "detail": "PYU*FLIPKART INTERNET Bangalore IND", "amount": 1000, "dc": "D"},
          {"tx_date": "2026-08-13", "detail": "COMPASS INDIA FOOD S Gurgaon IND", "amount": 250, "dc": "D"},
          {"tx_date": "2026-08-14", "detail": "HPCL PETROL PUMP Bangalore IND", "amount": 100, "dc": "D"}]}"""


@pytest.fixture
def llm(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    def set_reply(reply):
        monkeypatch.setattr(cards, "_llm_complete", lambda text: reply)
    return set_reply


def test_llm_parse_is_accepted_when_it_adds_up(llm):
    llm(GOOD_LLM)
    parsed, name = cards.parse_any("OTHER BANK statement text", allow_llm=True)
    assert name == "Claude" and len(parsed) == 1 and len(parsed[0]["txns"]) == 4
    assert sum(t["is_spend"] for t in parsed[0]["txns"]) == 3, "is_spend is derived here, not trusted from the model"


def test_llm_parse_is_rejected_when_totals_disagree(llm):
    """The gate that makes the fallback safe: a model that drops a line cannot slip through."""
    llm(GOOD_LLM.replace('"purchases": 1350', '"purchases": 9999'))
    with pytest.raises(ValueError, match="refusing to import"):
        cards.parse_any("OTHER BANK", allow_llm=True)


def test_llm_dropping_a_transaction_is_caught(llm):
    short = GOOD_LLM.replace(
        ',\n          {"tx_date": "2026-08-14", "detail": "HPCL PETROL PUMP Bangalore IND", "amount": 100, "dc": "D"}', "")
    assert short != GOOD_LLM
    llm(short)
    with pytest.raises(ValueError, match="refusing to import"):
        cards.parse_any("OTHER BANK", allow_llm=True)


@pytest.mark.parametrize("reply", ["I'm sorry, I can't read that.", "{}", "[]", '{"txns": []}',
                                   GOOD_LLM.replace('"dc": "D"', '"dc": "X"', 1)])
def test_llm_garbage_is_rejected_not_imported(llm, reply):
    llm(reply)
    with pytest.raises(ValueError):
        cards.parse_any("OTHER BANK", allow_llm=True)


def test_llm_reply_in_code_fences_is_still_read(llm):
    llm("```json\n" + GOOD_LLM + "\n```")
    assert cards.parse_any("OTHER BANK", allow_llm=True)[1] == "Claude"


def test_llm_not_used_unless_asked(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(cards, "_llm_complete", lambda t: pytest.fail("called without permission"))
    with pytest.raises(ValueError, match="unrecognised"):
        cards.parse_any("OTHER BANK", allow_llm=False)


def test_oversized_text_is_not_sent_to_claude(llm):
    llm(GOOD_LLM)
    with pytest.raises(ValueError, match="too large"):
        cards.parse_with_llm("x" * (cards.LLM_MAX_CHARS + 1))


@needs_pdfs
def test_browser_style_upload_of_real_statements(seeded_db, client):
    """Upload the way the page does, over multipart, including a wrong password first."""
    files = [("files", (os.path.basename(p), open(p, "rb"), "application/pdf")) for p in PDFS[:2]]
    wrong = client.post(f"{API}/cards/upload", data={"password": "nope"}, files=files).json()["files"]
    assert all(not f["ok"] and "wrong password" in f["error"] for f in wrong)
    files = [("files", (os.path.basename(p), open(p, "rb"), "application/pdf")) for p in PDFS[:2]]
    ok = client.post(f"{API}/cards/upload", data={"password": PASSWORD}, files=files).json()["files"]
    assert all(f["ok"] and f["parser"] == "SBI Card" for f in ok), ok
