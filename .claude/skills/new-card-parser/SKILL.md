---
name: new-card-parser
description: Add a credit-card statement parser for a new bank or layout (spendlens/cards_<bank>.py), or fix one that misreads a statement. It must reconcile to the statement's printed totals and be registered in cards.PARSERS. Hands the work to the card-parser subagent.
argument-hint: <bank / card, and where a sample statement is, e.g. "Axis Magnus - screenshot/axis/">
---

Parser requested: **$ARGUMENTS**

1. Find the sample. A parser written without the statement's real text is a guess. Ask the user for a sample PDF
   path (they usually live under `screenshot/`, which is git-ignored) and its password if it has one. Have them
   set the password as an env var in the command (e.g. `SPENDLENS_<BANK>_PASSWORD`), not paste it into chat or a
   file. If there's no sample, say the parser will be untested against the real format and confirm before going on.
2. Extract the text the parser will see, without writing it into the repo:
   `.\venv_expense\Scripts\python -c "import os, sys; sys.path.insert(0, 'spendlens'); import cards; print(cards.read_pdf(r'<pdf path>', password=os.environ.get('SPENDLENS_<BANK>_PASSWORD', ''))[:6000])"`
   (`read_pdf` takes a path or file object and also reads `.xlsx` statements). Note which existing parser's layout it resembles, and that no
   existing `detect` in `cards.PARSERS` already claims it (an existing parser misreading it is a fix, not a new
   parser).
3. Hand the work to the **card-parser** subagent with the Agent tool. Give it: the bank and card, the PDF path and
   password env var name, the closest existing parser, and what you saw in the text (totals block, transaction
   line shape, points, international markers). Remind it that real names, card numbers and statement text must not
   be committed. Test statements are synthetic.
4. When it reports back, verify: it's registered in `PARSERS`; a test proves totals that don't add up raise
   `ValueError`; `cards.parse_any` routes the sample to it; the whole cards suite still passes
   (`python -m pytest tests/test_cards*.py tests/test_card_*.py -q`). Then grep the new test file for the card number
   digits, the cardholder's name and other personal details from the sample.
5. Tell the user: what it parses, the reconciliation identity, the test output, and anything it guessed.
