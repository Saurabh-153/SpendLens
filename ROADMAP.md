# SpendLens roadmap

Where the app goes from tracker to a wealth platform. Credit cards have their own
document: [CREDIT_CARDS.md](CREDIT_CARDS.md). The forecasting / ML notes in
[spendlens-forecasting-ml-plan.md](plan/spendlens-forecasting-ml-plan.md) are Phase 5 here.

## Where things stand (Oct 2026)

Built and working: the Expense month grid with sub-categories and effective-dated
targets, Holdings with accrual valuation for FD / RD / PF, the Ledger with XIRR and
FY gains, daily Yahoo + AMFI prices, the Asset Mix tab with a SIP-only path to a
target Equity / Gold / Debt ratio, a Monte Carlo goal projection, and six admin
tools. About 7,000 lines, 60 endpoints, one SQLite file.

Three things separate this from Kuvera / INDmoney / Personal Capital:

1. **Data arrives by hand.** Everything is typed. They import statements.
2. **Net worth is incomplete.** Only assets are modelled. No loans, no card dues,
   no property, so "net worth" is really "portfolio value".
3. **There is no single planning engine.** Goals, mix and forecast each answer a
   slice of "will I get there, and what do I change".

Phase 1 attacks exactly those three.

## Design rule

> **One number has one home, one engine, one name.**

A feature ships only if it removes a decision rather than adding a screen. Every
phase below is checked against that rule before it is called done.

## Redundancy register — remove before adding

The app has grown two of several things. Cleaning this up is cheaper than building
on top of it, and it is the main source of contradictory design today.

| # | Redundancy | Resolution |
|---|---|---|
| 1 | **Two target systems**: `portfolio_plan.targets` by group (Admin → Target allocation, drift on the Portfolio dashboard) and `mix_targets` by exposure (Admin → Target mix, Asset Mix page) | Exposure is the risk axis and the only target. Group targets retire; `holding_groups` becomes purely custodial — *where it is held*. One "Target mix" card in admin. |
| 2 | **Two projection engines**: group-based Monte Carlo goal odds and the exposure-based deterministic `mix_summary` | One `projection.py` with two modes — deterministic median path and Monte Carlo bands — from the *same* per-exposure return and volatility assumptions. Goals, mix path and forecast all call it. |
| 3 | **Two XIRRs**, snapshot-derived and ledger-derived, switched by a 50 % coverage rule | Ledger XIRR is the only XIRR. The snapshot series feeds TWR instead, and both are shown labelled: "your money" (XIRR) vs "the holding" (TWR). |
| 4 | `sector` repurposed as "Institution / purpose" while `tags` carry sector, and `grp` sometimes repeats both | Rename the column to `institution`. Sector and theme live only in `tags`. |
| 5 | A group named **Equity** next to the exposure **Equity** | Rename the group to **Stocks**. Needs explicit sign-off: it touches `holdings.grp`, `holding_groups` and the targets JSON. |
| 6 | Dead tables `users`, `rebalance_targets`, `price_alerts`, legacy `settings` | Dropped in a versioned migration, backup first. `price_alerts` returns properly in Phase 3. |
| 7 | "Worth a look" built separately on the Expense dashboard and on Holdings | One `insights.py` rule engine, one card style, used by both. |
| 8 | Net worth printed on the Holdings KPI, the Portfolio KPI and in the donut centre | Net worth lives on the Overview page. Every other page shows its own subject. |
| 9 | MF / FD / PF stored as `qty 1 × amount` while MFs also carry `units` / `nav` | Normalised in Phase 1A: a position has units + price **or** invested + value, never a fake quantity. |
| 10 | Five top-level pages plus three dashboard tabs, with net worth spread across them | Nav becomes **Overview · Spending · Investments · Cards · Admin**. Ledger and Asset Mix become tabs inside Investments. |

## Phases

### Phase 0 — Foundation
Nothing user-visible. Everything after it is cheaper and safer.

- **A test suite.** `pytest` with a fixture-DB builder and a `TestClient` shape test
  for every existing endpoint. There is no test suite today, which is the single
  biggest risk to the rest of this roadmap.
- **Versioned migrations.** `schema_migrations(version, applied_at)` and a `migrate(db)`
  chain in `database.py`, each step taking a timestamped backup, replacing the current
  ad-hoc `ALTER TABLE` checks.
- Redundancy register items 1, 2, 3, 4, 6 and 7.
- `user_id INTEGER DEFAULT 1` on every user-owned table now, so Phase 4 is a login
  rather than a rewrite.
- CI: typecheck, build and pytest on push.

### Phase 1A — True net worth: accounts and liabilities
- An `accounts` table with `kind` in `bank | card | loan | investment | property | insurance`.
  `holdings` become the positions inside investment accounts.
  **Net worth = assets − liabilities**, with a liabilities block on Overview.
- `loans`: principal, rate, tenure, EMI, start date → an amortisation schedule,
  interest paid to date, outstanding, and a **prepayment what-if**
  ("₹2L now saves ₹6.4L of interest and 19 months").
- Property, gold in a locker and insurance surrender value as manually valued accounts.
- **Overview page**: net worth with a 12-month trend, assets vs liabilities, savings
  rate, emergency cover, and the next 30 days of obligations — EMIs, card dues,
  maturities, premiums.

### Phase 1B — Automated data in
The usability jump. It reuses the `subcategory_rules` pattern and the "Needs review"
queue that already exist.

**The interface is a folder.** `statements/inbox/` is where you drop files;
`processed/` and `failed/` are where they end up; `rules/` holds the saved column
mappings per bank format.

- A **Scan folder** button (and a scan at start-up), never a silent background
  watcher: scanning is automatic, committing is not. Each scan ends in a review
  screen, and rows are written only when you approve them.
- **Format detected from the content**, not the filename — the header row is matched
  against a registry of known layouts (bank savings, card statements, broker
  tradebooks, CAS eCAS). An unknown layout opens a one-time column mapper whose
  result is saved to `rules/`, so that format is recognised from then on.
- **Two hashes**: one per file, so the same file twice is skipped at once, and one per
  row over (account, date, amount, normalised narration), because overlapping date
  ranges between statements are the normal case rather than the exception.
- **The account is resolved before parsing** — a row's identity depends on it. Either
  from the sub-folder (`inbox/hdfc-savings/…`) or chosen per file at review time.
  This is why `accounts` (Phase 1A) has to land before this phase.
- CSV and XLSX first; **PDF after**, because card-statement text extraction is
  brittle. Every import is checked against the statement's own total and is rejected
  whole rather than applied in part.

- `imports(id, account_id, kind, filename, file_hash, rows, status, created_at)` plus an
  `import_rows` staging table, so an import is replayable and reversible.
- Importers: bank CSV, credit-card statement CSV then PDF, broker tradebook / P&L CSV,
  and **CAMS / NSDL eCAS** — one file reconstructs the whole MF and demat portfolio.
  AMFI NAVs already arrive this way.
- Dedupe on a hash of (account, date, amount, normalised narration).
- Categorisation: merchant normalisation → rule match → a learned prior from your own
  history → a review queue for the rest. Every decision you make becomes a rule.
- **Acceptance:** a month of bank and card statements goes from file to categorised,
  deduped and reconciled in under two minutes, with no typing.

### Phase 1C — Cashflow and planning engine
- A monthly **cashflow statement**: income − spend − EMI − premiums − SIP = surplus,
  with the surplus reconciled against the actual change in net worth. The gap is a
  data-quality check that catches anything missing.
- `projection.py` powers goals with **inflation** and priority, a retirement corpus and
  FIRE number, "the money runs out in year N", and a shortfall fix stated three ways:
  "₹8.2k a month more, or retire 14 months later, or trim the goal by 11 %".
- A **goal-aware glide path**: the target mix shifts towards Debt as a goal approaches,
  instead of one constant target forever.
- Adequacy checks: life cover against 10× income, emergency fund against six months of
  *actual* spend — a number the dashboard already computes.

### Phase 2 — Performance, risk, rebalancing, tax
- **TWR and XIRR**, both labelled. **Benchmark compare** against Nifty 50 TRI, gold and
  a debt index from free sources, following the `prices.py` pattern. Drawdown curve and
  rolling 1 / 3 / 5-year returns.
- **Risk**: concentration (HHI and top-5 weight), an equity beta proxy, mutual-fund
  portfolio overlap, and a short risk-profile questionnaire that *suggests* the target
  mix instead of leaving you to guess 60/10/30.
- **Rebalancing**, one engine, three modes: SIP-only (exists today), lump-sum, and
  tax-aware selling that checks LTCG / STCG, exit load and lock-ins. Drift bands of
  ±5 points, so it speaks only when it matters.
- **Tax**: FY realised gains split STCG / LTCG with the ₹1.25L equity exemption and
  grandfathering, FD *accrued* interest for the ITR, a dividend and TDS summary, an
  80C / 80D / NPS tracker, and loss-harvesting suggestions before 31 March.

### Phase 3 — Insights, alerts, reporting, polish
- One `insights.py` and an `alerts` rule set with severity and snooze. A monthly digest
  (PDF or HTML) covering net worth, cashflow, mix drift and actions due.
- Spend anomaly detection (this is `plan/spendlens-forecasting-ml-plan.md` Phase B3).
- UX: a ⌘K command palette and global search, a real mobile layout, "explain this
  number" on every computed figure, and consistent empty states. The keyboard-first
  Expense grid is the model every other page should follow.

### Phase 4 — Multi-user and hosting
Login with sessions and hashed passwords, per-user isolation on the `user_id` columns
added in Phase 0, backup / restore and export-everything, an audit log, rate limiting,
and a Postgres option behind the existing DB layer.

### Phase 5 — ML
[spendlens-forecasting-ml-plan.md](plan/spendlens-forecasting-ml-plan.md) as written: A+ lumpy annual payments, B real models, C stored
forecasts and accuracy tracking — now with the imported transaction history from
Phase 1B to learn from.

## Deliberately not doing

Live bank aggregation and Account Aggregator integration (needs a licensed partner),
broker order placement, anything phrased as a recommendation to buy a specific
security, social or leaderboard features, and a native mobile app. Statement import
delivers most of aggregation's value with none of its risk.

## Code shape this implies

| Area | Change |
|---|---|
| `spendlens/database.py` | migration framework, the new tables, `user_id` columns |
| `spendlens/portfolio.py` | keeps KPIs; the mix and goal maths (`mix_summary`, `_simulate_mix`, `_solve_split`, the Monte Carlo) move into `projection.py` as two modes of one engine |
| `spendlens/ledger.py` | the single XIRR source; its gains feed `tax.py` |
| New modules | `projection.py`, `insights.py`, `imports/` (bank, card, eCAS, broker), `tax.py`, `cards.py`, `loans.py` |
| `spendlens/routes/api.py` | 1,500 lines — splits into `routes/expenses.py`, `portfolio.py`, `cards.py`, `imports.py`, `admin.py` under the same `/spendlens/api` prefix |
| Frontend | the five-item nav in `App.tsx`; new `Overview.tsx`, `components/cards/`, `Import.tsx`; `ExposureDashboard.tsx` and `MixPlan.tsx` move under Investments; `exposure.ts`, `names.ts`, `theme.ts` and `ui.tsx` are reused unchanged |

## How each phase is verified

- Every phase: `pytest` against a **copy** of the database, never the live file;
  `pnpm run typecheck` and `pnpm build`; the dataviz palette validator on any new chart.
- Phase 1A: net worth equals Σ assets − Σ liabilities computed by hand from the data,
  and an amortisation schedule reproduces a known EMI to the rupee.
- Phase 1B: re-importing the same statement adds zero rows, and a deliberately
  shuffled and duplicated file still reconciles to the statement total.
- Phase 1C: the deterministic path equals the P50 of the Monte Carlo within tolerance —
  the proof that the two old engines really have become one.
- Visuals are never verified automatically. Each phase ends with a short list of what
  to look at in the browser.

## Open items

1. The group rename **Equity → Stocks** and two tag fixes (Bajaj Housing Finance →
   Finance; the SGB's `sector`) are database writes awaiting sign-off.
2. A **locked** flag for SIPs that cannot be redirected, such as the ₹40,000 PF
   contribution. The mix plan currently assumes every rupee of SIP is movable, which
   overstates how fast Equity can rise.
3. The real target mix, expected returns and reach window. 60/10/30 and 12/8/7 are
   placeholders.
4. The list of credit cards held, so the card module ships with real rules seeded.
