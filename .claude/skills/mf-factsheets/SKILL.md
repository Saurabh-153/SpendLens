---
name: mf-factsheets
description: Read the month-wise mutual-fund factsheets and portfolio disclosures in fund_fact_sheet/ (PDF / Excel, flat or in YYYY-MM sub-folders), extract the user's funds with the mf-factsheet-analyst subagent, verify the extraction, and load it into SpendLens so the MF Analysis page (scorecard, factsheet analysis / buying trend, anomalies, overlap) shows real data. Use when the user adds factsheets or asks to update MF Analysis.
argument-hint: "[folder, default fund_fact_sheet] [month YYYY-MM or year to limit to]"
---

Request: **$ARGUMENTS** (folder defaults to `fund_fact_sheet`).

1. **What's new.** `.\venv_expense\Scripts\python spendlens\mf_extract.py inventory <folder>`. List the files with status
   `new` / `changed` (limit to the month or year in the arguments if one was given), and anything `unsupported` or
   `month-unknown`. If nothing is new, say so and ask whether to re-import what's already extracted (go to step 5).
2. **Which funds.** `.\venv_expense\Scripts\python spendlens\mf_extract.py funds` lists the MF holdings (name, AMFI code).
   If it can't reach the database, ask the user which funds they hold (or read `factsheets/funds.txt` if it exists).
   Several folios of one fund are **one** fund: pass each scheme once.
3. **Portfolio disclosures (Excel) need no AI.** Save the funds list to a file and, for each new disclosure, run
   `.\venv_expense\Scripts\python spendlens\mf_extract.py disclosure <file> --funds <funds.json> --amc "<AMC name>" --write`.
   It finds each held fund's sheet and the header row (ISIN, Quantity, % to NAV) by their names, converts % printed as a
   fraction, dates the file from its "as on" line, and reports lines, total % (should be about 100) and lines with share
   counts per fund. A balancing "Net Receivables" line printed in another unit is recomputed and noted. Check the report;
   a fund not found or a total far from 100 needs a look before importing.
4. **Factsheet PDFs from AMCs with a fixed parser (no AI): Axis, Edelweiss** (`spendlens/mf_parsers.py`, `PARSERS`). For
   each held scheme: `.\venv_expense\Scripts\python spendlens\mf_extract.py factsheet <pdf> --amc axis|edelweiss --scheme
   "<name as printed>" --amfi <code> --category "<category>" --amc-name "<AMC>" --write`. It locates the scheme's pages,
   reads them by position, dates the file from the page (Edelweiss names files by the month they are *published*), and
   reports every field, so check the report: AUM, expense ratio, ratios and returns non-null, holdings total near 100%
   (Axis) or 10 lines (Edelweiss prints only its top 10). Several schemes from one file land in the same JSON.
   **Other AMCs' PDFs:** hand the work to the **mf-factsheet-analyst** subagent with the Agent tool. Give it the folder, the exact
   files to do (with their sha256 from step 1) and the funds list. With many months, start one subagent per month in
   parallel, or one per quarter for a long backlog (a month is a factsheet plus a disclosure). Each writes only its own
   `<folder>/_extracted/<month>/`. Remind it: printed numbers only, null for anything not printed, one JSON per
   source file, and validate before reporting. When the AMC also publishes disclosures, the agent leaves the factsheet's
   holdings out (the disclosure has them all, with share counts).
5. **Verify its report** before importing:
   - every file it was given has a JSON, and `mf_extract.py validate <json>` says `"ok": true` for each;
   - spot-check two figures per file yourself (an expense ratio and one holding's %): `mf_extract.py locate <pdf> "<scheme>"`
     (or `find` for an Excel sheet), then `text <file> --pages <range>`, and compare. Never read a whole PDF;
   - list the held funds it didn't find.
   Fix or re-run anything wrong. Don't import a file you doubt.
6. **Import.** `import_mf.py` must run with the backend **stopped**: it refuses otherwise, because both would write the
   SQLite mirror. If the backend is running (port 5000 answers), ask the user to stop it, or stop it with their OK. Then
   run `.\venv_expense\Scripts\python spendlens\import_mf.py <folder>`. It validates everything again and imports all
   files or none. Morningstar fund reports (`morningstarreport*.pdf`) in the folder are parsed directly
   (`mf_parsers.parse_morningstar`) and stored in `mf_reports` (with the PDF itself, shown on MF Analysis › Morningstar check); nothing to extract.
   The user wants the source files gone once they're in the database: add `--delete-imported`, which deletes only files
   whose sha256 the database holds (never a file not yet extracted); a file open in another program is kept and listed. Tell the user to start the backend again
   (`.\venv_expense\Scripts\python spendlens\app.py`).
7. **Report** to the user: months and files read, funds extracted and matched to their holdings, holdings not found in
   any factsheet (the import prints them), new anomalies, and the strongest buying-trend items from the latest month
   (e.g. "3 of your funds added Bharti Airtel"). Point them to MF Analysis › Factsheet analysis.

Notes: factsheets and portfolio disclosures are public AMC documents. `fund_fact_sheet/` and `factsheets/` (with their
`_extracted/`) are git-ignored: never commit them. Re-running is safe: a re-extracted file replaces its earlier import.
