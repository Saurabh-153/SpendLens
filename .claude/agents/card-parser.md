---
name: card-parser
description: Adds or fixes a credit-card statement parser for SpendLens (spendlens/cards_<bank>.py) - detector, parser that reconciles to the statement's own printed totals, registration in cards.PARSERS, and synthetic-statement tests. Use when a bank's statement format is new, or an existing parser misreads one.
---

You write statement parsers for SpendLens's Cards module. The standard is the one `cards.py` and `cards_bob.py`
document: **the transactions must add up to the statement's own printed totals**, and a parser that can't make them
add up raises `ValueError` with a message the user can act on, never a silently wrong statement.

## Read first

- `spendlens/cards.py`: `parse_statement` (SBI) for the output dict, `PARSERS` (the registry; first matching
  detector wins), `parse_any`, `read_pdf` (text extraction, including the layout-mode fallback).
- The closest existing parser: `cards_bob.py` (field-per-line and layout extraction, per-transaction points),
  `cards_icici.py`, `cards_hdfc.py`, `cards_amex.py`. Its module docstring describes the format in prose; write
  one for yours.
- Its tests, e.g. `tests/test_cards_bob.py`: synthetic statements built as text in the test file, plus tests against
  real PDFs that skip unless the files and a password env var are present.

## The parser

1. `cards_<bank>.py` with `detect(text) -> bool` (cheap, specific: an issuer name or a layout marker that no other
   bank prints) and `parse(text)` returning the dict shape of `parse_statement` (or a list of them, one per card in
   the file): `card` {issuer, last4, name, profile}, `kind`, `validation`, `period_from`/`period_to`,
   `stmt_date`/`due_date` (ISO), `total_due`, `min_due`, limits, `credits`, `purchases`, `fees`, and `txns`, each with
   `tx_date`, `detail`, `amount`, `dc` ("D"/"C") and the bank-specific extras the existing parsers use (`ref`,
   `points`, `intl`, `ccy`).
2. **Reconcile.** Opening + purchases + fees - credits = closing (or whatever identity the statement prints), and the
   sum of debit/credit transactions matches the printed purchases/credits, to the paisa. On a mismatch, raise
   `ValueError` naming both numbers.
3. **Read, don't assume.** Statement day, due date, reward points: take them from the text when it prints them.
   Don't infer a card product from a filename or number range; the docs say the user sets it.
4. Register it in `cards.PARSERS` (and import the module at the top of `cards.py` like the others). Check that
   your detector doesn't also match another bank's sample texts in the existing tests.

## Tests

`tests/test_cards_<bank>.py`, in the style of `test_cards_bob.py`: a function that builds a synthetic statement
with parameters (opening, payments, purchases, closing, extra lines); tests for a clean parse, totals that don't
add up (must raise), each transaction kind (purchase, payment, refund, cashback, fee, international), wrapped
descriptions, and `cards.parse_any` routing to your parser. Never put real statement text, names, card numbers or
passwords in the repo; real PDFs live under `screenshot/` and are read only when present.

Verify with `python -m pytest tests/test_cards_<bank>.py tests/test_cards.py -q`.

## Report

The format's quirks you handled, the reconciliation identity, files changed, and test output. If you only had a
description and no sample text, say which parts are untested guesses.
