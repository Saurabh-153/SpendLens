# SpendLens data model

One schema, two databases: PostgreSQL (when `DATABASE_URL` is set, normally from `.env.local`) and the SQLite file `spendlens/spendlens_v2.db`. One of them is the main database and the other holds a verified copy of it (see *Two databases* below); without `DATABASE_URL` the SQLite file is the only database. See [README.md](README.md) for the rest of the project.

```mermaid
erDiagram
    users ||--o{ auth_sessions : "signed in"
    users ||--o{ module_grants : "modules enabled"
    users ||--o{ access_requests : "asks for a module"
    mf_sources ||--o{ mf_fund_months : "source_id"
    mf_fund_months ||--o{ mf_holdings : "portfolio that month"
    mf_reports }o--o{ mf_fund_months : "cross-checked by scheme_key + month"
    holdings }o--o{ mf_fund_months : "matched by AMFI code or name"
    categories ||--o{ expenses : "has"
    reminder_categories ||--o{ reminders : "groups"
    categories ||--o{ reminders : "watched for the done tick"
    subcategories ||--o{ reminders : "optional narrower match"
    categories ||--o{ portfolio_goals : "recurring expense, planned vs spent"
    categories ||--o{ subcategories : "has"
    categories ||--o{ category_targets : "target history"
    categories ||--o{ subcategory_rules : "note rules"
    subcategories ||--o{ expenses : "optional label"
    subcategories ||--o{ subcategory_rules : "rule result"
    holdings ||--o{ transactions : "ledger"
    holdings ||--o{ sip_log : "SIP applied"
    holdings ||--o{ price_history : "daily price"
    holdings ||--o{ holding_snapshots : "daily value"
    holding_groups ||--o{ holdings : "grp (by name)"
    equity_trades }o--o{ equity_events : "replayed together per account and symbol"
    equity_dividends }o--o{ equity_trades : "qty checked against the replay"
    broker_holdings }o--o{ equity_trades : "share counts reconciled"
    equity_audit ||--o{ equity_trades : "import_id"

    categories {
        int id PK
        int user_id
        text name
        text icon
        text color
        int target_pct "legacy; targets live in category_targets"
        text hint "shown in the add dialog"
        int visible
        int sort_order
        text start_month "first month shown, 0000-00 = always"
        text end_month "last month shown, NULL = active"
    }
    category_targets {
        int category_id PK,FK
        text from_month PK "effective-dated"
        real target_pct "percent of salary"
    }
    budget_history {
        int id PK "surrogate id (Alembic 459d2bc3ff86)"
        int user_id "default 1; unique with from_month"
        text from_month "effective-dated, 0000-00 = initial"
        int income "monthly salary"
        real savings_amount "fixed saving in rupees"
    }
    subcategories {
        int id PK
        int category_id FK
        int user_id
        text name
        int sort_order
        text start_month
        text end_month
    }
    subcategory_rules {
        int id PK
        int category_id FK
        int user_id
        text pattern
        text match_type "contains or exact"
        int subcategory_id FK
    }
    reminder_categories {
        int id PK
        int user_id "default 1"
        text name
        text color "hex, e.g. #f5b942"
        text kind "NULL / card / sip - where automatic card and SIP dates land; not deletable"
        int sort_order
    }
    reminders {
        int id PK
        int user_id "default 1"
        int category_id FK
        text name
        real amount "0 = no amount"
        int day "1-31; clamped to the month's last day"
        text repeat "monthly / quarterly / yearly"
        int month "1-12, only for quarterly / yearly"
        bool enabled
        text note
        int expense_category_id FK "expenses in this category in the month tick it done; ON DELETE SET NULL"
        int expense_subcategory_id FK "optional: only this sub-category counts"
        text source_key "category_id:subcategory_id when kept from a suggestion"
        text created_at
    }
    reminder_settings {
        int user_id PK "default 1"
        bool nudge_on
        text nudge_time "HH:MM, local"
    }
    vacations {
        int id PK
        int user_id "default 1"
        text name
        text start_date "YYYY-MM-DD, inclusive"
        text end_date "YYYY-MM-DD, inclusive; a vacation spans at most 366 days"
        text color "#rrggbb"
        text created_at
    }
    reminder_overrides {
        int id PK
        int reminder_id FK "unique with month"
        text month "YYYY-MM"
        int day "this month's occurrence moved here"
    }
    trackers {
        int id PK
        int user_id "default 1"
        text name
        text color "#rrggbb"
        int target_per_week "1-7"
        text weekdays "csv, 0 = Monday"
        text pause_on "csv of vacation / IN / US"
        int bill_reminder_id FK "nullable; cost per visit"
        int sort_order
        text created_at
    }
    tracker_days {
        int tracker_id PK, FK
        text date PK "YYYY-MM-DD ticked"
    }
    tracker_cost_links {
        int id PK
        int tracker_id FK
        int expense_category_id FK
        int expense_subcategory_id FK "nullable = whole category"
    }
    expenses {
        int id PK
        int category_id FK
        int user_id
        int subcategory_id FK "NULL = Unassigned"
        text date "YYYY-MM-DD"
        real amount
        text note
        real cashback
        text created_at
    }
    holding_groups {
        int id PK
        int user_id
        text name "display group, matches holdings.grp"
        int sort_order
        text hidden_columns "Holdings columns hidden for this group"
    }
    holdings {
        int id PK
        int user_id
        text name
        text ticker "NSE symbol"
        text asset_type "EQ MF FD PF GOLD CASH"
        text exposure "Equity Gold Debt Cash - what the money is really in"
        text tags "extra labels, comma separated"
        text sector
        real qty
        real buy_price
        real cmp "current price / value"
        real week52_low "from Yahoo"
        real week52_high
        text notes
        int visible "0 = hidden from Holdings"
        text created_at
        text grp "display group"
        real sip_amount "monthly SIP"
        int sip_day
        text sip_applied "last month a SIP was applied"
        int sip_reminder "1 = shown on the reminder calendar and in the feed (Alembic c4e6a9b2d7f1)"
        real rate "fixed interest % p.a."
        text start_date "opening date"
        text compounding "Q A or S"
        int rd "1 = recurring deposit"
        text credits "interest credited"
        int manual "1 = keep typed value"
        text maturity
        text scheme_code "AMFI code (MF)"
        real units "MF units"
        real nav "latest NAV"
        int auto_price "1 = daily price update"
        text price_date
        text price_note "last failure reason"
    }
    equity_trades {
        int id PK
        int user_id
        text account "user's demat label (SK, SS)"
        text client_id "broker id from the file"
        text symbol
        text isin
        text trade_date
        text side "BUY SELL"
        real qty
        real price
        text exchange
        text trade_id "broker ids, part of the fingerprint"
        text order_id
        text executed_at
        text fingerprint "unique per user: re-imports add nothing"
        int import_id "equity_audit row"
    }
    equity_events {
        int id PK
        int user_id
        text account "empty = every account"
        text symbol
        text ex_date
        text kind "SPLIT BONUS BUYBACK IPO TRANSFER_IN/OUT ADJUST DEMERGER MERGER RENAME"
        real ratio_new
        real ratio_old
        real qty
        real price "NULL = cost unknown"
        text target_symbol
        real cost_pct "demerger cost moved"
        text note
        text source "manual / yahoo"
        text created_at
    }
    equity_dividends {
        int id PK
        int user_id
        text account
        text symbol
        text ex_date
        real qty
        real dps
        real amount
        text source "zerodha statement / yahoo"
        text raw_symbol "as the statement printed it"
        int import_id "equity_audit row"
        text updated_at
    }
    broker_holdings {
        int id PK
        int user_id
        text account
        text symbol
        text isin
        real qty
        real avg_price "broker's average cost"
        text as_of
        int import_id "equity_audit row"
    }
    equity_securities {
        int id PK
        int user_id
        text symbol
        text yahoo_symbol "override"
        text name
        real last_price
        text price_date
        text fetch_error "last Yahoo failure"
    }
    equity_audit {
        int id PK
        int user_id
        text at
        text kind "tradebook dividends holdings refresh event"
        text account
        text file_name "the imported file"
        text period_from
        text period_to
        text summary
        text detail "JSON: what changed"
    }
    transactions {
        int id PK
        int holding_id FK "NULL for unlinked dividends"
        text name "for unlinked rows"
        text tx_date
        text kind "BUY SELL DIVIDEND OPENING"
        real qty
        real price
        real amount
        real fees
        real realized "gain at average cost"
        text note
        text source "manual / sip / import-sheet"
        int applied "1 = holding was updated"
        int user_id
    }
    sip_log {
        int id PK
        int holding_id FK
        text holding_name "kept if the holding is deleted"
        text month "one row per holding and month"
        text sip_date
        real amount
        text applied_at
        int user_id
    }
    price_history {
        int holding_id PK,FK
        text price_date PK
        real price
    }
    price_runs {
        int id PK
        text ran_at
        int ok
        int updated
        int failed
        text detail
    }
    portfolio_snapshots {
        int id PK "surrogate id (Alembic 0a3ec7a2c0e3)"
        int user_id "default 1; unique with snap_date"
        text snap_date "one row per user per day"
        real total "net worth"
        real invested
        text groups "JSON value by group"
    }
    holding_snapshots {
        int id PK
        int holding_id FK
        text snap_date "one row per holding per day; unique with holding_id"
        real qty
        real cmp
        real present
        real invested
    }
    portfolio_goals {
        int id PK
        int user_id "default 1"
        text name
        real target_amount "for recurring: the amount in the first year"
        int target_year "for recurring: the first year"
        text kind "large / small / recurring (Alembic c7e2f9a4b1d3)"
        int target_month "1-12, nullable; a year alone counts as June"
        int every_months "recurring: repeat interval, default 12"
        int end_year "recurring: last year, nullable"
        real escalation_pct "recurring: yearly rise"
        int category_id "recurring: nullable, planned vs spent (no FK)"
        int subcategory_id "nullable"
    }
    portfolio_plan {
        int id PK "surrogate id (Alembic 0a3ec7a2c0e3)"
        int user_id "default 1; unique with key"
        text key "targets, assumptions"
        text value "JSON"
    }
    schema_migrations {
        int version PK
        text name
        text applied_at
    }
    card_accounts ||--o{ cards : "share one bill"
    cards ||--o{ card_statements : "monthly cycle"
    cards ||--o{ card_txns : "spend"
    cards ||--o{ card_merchant_rules : "class override"
    cards ||--o{ card_perks : "benefits"
    card_statements ||--o{ card_txns : "appeared on"
    card_accounts {
        int id PK
        int user_id "default 1 (Alembic 7fa60c624af4)"
        text issuer
        text label
    }
    cards {
        int id PK
        int user_id
        int account_id FK "cards on one bill share it"
        text name
        text issuer
        text network
        text last4
        real credit_limit
        real cash_limit
        int statement_day
        int due_day
        real annual_fee
        real fee_waiver_spend "annual spend that waives the fee"
        real rate_online "generic profile: percent online"
        real rate_offline "generic profile: percent offline"
        text profile "sbi_cashback / icici_amazon / generic: reward classes and rules"
        text rates "JSON percent per reward class"
        real cashback_cap "most earnable in one cycle, 0 = uncapped"
        int grace_days "days from statement to due date"
        int pay_buffer_days "days before the due date to pay"
        real float_rate "percent a year idle money earns"
        int cycle_verified "1 = cycle read from a statement, 0 = assumed"
        text status "active / downgrade / closed"
        text notes
        int perks_seeded "1 = starter benefits were written in"
        text color "fixed display colour, '' = auto-assigned"
        int sort_order "drag position on the Cards page"
    }
    card_statements {
        int id PK
        int card_id FK
        text kind "cycle (monthly) or year (a yearly list)"
        text period_from
        text period_to "unique per card"
        text stmt_date
        text due_date
        real total_due
        real min_due
        real purchases "the statement's own spend total"
        real credits
        real fees
        real available_credit
        real cashback_reported "what was actually paid"
        real cashback_calc "what the rules say"
        text file "the uploaded file name; the PDF is not kept"
        text imported_at
        int points_earned "reward points the statement says were earned"
        int points_balance "closing points balance"
    }
    card_txns {
        int id PK
        int card_id FK
        int statement_id FK
        text row_hash "unique; de-duplicates overlapping statements"
        text tx_date
        text detail "the raw statement line"
        text merchant
        text city
        real amount
        text dc "D spend, C payment or credit"
        int emi "converted to EMI"
        int is_spend "1 for purchases and EMI instalments"
        text kind "spend / refund / payment / cashback / emi_principal / fee"
        text ref "bank reference number, where one is printed"
        text cls "reward class, from the card profile"
        text ccy "foreign currency code, empty for rupees"
        int points "reward points printed on the line (BOB)"
        text category "the bank's merchant category"
        real cashback
        int capped
    }
    card_merchant_rules {
        int id PK
        int user_id "default 1 (Alembic 7fa60c624af4); card_id can be NULL, so this says whose 'every card'"
        int card_id FK "NULL applies to every card"
        text pattern
        text match_type "contains / prefix / regex"
        text cls
        text created_at
    }
    card_perks {
        int id PK
        int card_id FK
        text kind "reward / milestone / lounge / fee / exclusion / cap / other"
        text title
        text detail
        real value_yr "what it is worth a year, in rupees (optional)"
        text source
        int checked "1 = confirmed against the card's own terms"
        int sort
        text updated
    }
    users {
        int id PK
        text email "unique, lower-case"
        text name
        text password_hash "bcrypt"
        text role "admin / user"
        bool is_active "false = cannot sign in"
        text created_at
    }
    auth_sessions {
        text token_hash PK "sha256 of the cookie; the cookie itself is never stored"
        int user_id FK
        text expires_at "30 days after sign-in"
        text created_at
    }
    module_grants {
        int id PK
        int user_id FK
        text module "expense / holdings / ledger / cards; unique with user_id"
        int granted_by FK "the admin"
        text granted_at
    }
    access_requests {
        int id PK
        int user_id FK
        text module "the module asked for"
        text note
        text status "pending / approved / rejected"
        text created_at
        int decided_by FK "the admin, nullable"
        text decided_at
        text decision_note
    }
    app_prefs {
        text key PK "e.g. the Holdings column layout per user"
        text value "JSON"
    }
    mf_sources {
        int id PK
        int user_id
        text month "YYYY-MM the file is as on; unique with file_name"
        text as_on "the exact date printed"
        text file_name
        text sha256 "of the source file: --delete-imported removes only files whose hash is here"
        text kind "factsheet / portfolio"
        text amc
        int funds "funds read from it"
        text notes
        text imported_at
    }
    mf_fund_months {
        int id PK
        int user_id
        text month "unique with scheme_key"
        text as_on
        text scheme_key "normalised scheme + plan: the identity across months"
        text scheme
        text plan "Direct / Regular"
        text amc
        text amfi_code "matches holdings.scheme_code"
        text category
        text benchmark
        real aum_cr "month-end AUM, crore; every figure NULL when not printed"
        real ter_pct "expense ratio"
        real std_dev
        real beta
        real sharpe
        real alpha
        real treynor
        real turnover_pct
        real top10_pct "top-10 holdings share"
        real cash_pct
        real cap_large
        real cap_mid
        real cap_small
        real ret_1y
        real ret_3y "CAGR as printed"
        real ret_5y
        real bench_1y
        real bench_3y
        real bench_5y
        real ytm
        real mod_duration
        real avg_maturity
        real macaulay
        real credit_aaa_sov_pct "debt funds"
        text fund_manager "names, A, B"
        text managers "JSON name + managing since"
        text notes
        int source_id "the mf_sources row it came from"
    }
    mf_holdings {
        int id PK
        int user_id
        int fund_month_id FK "ON DELETE CASCADE"
        text name
        text isin
        real pct "percent of the fund"
        text sector
        text rating
        real qty "shares, from a portfolio disclosure"
    }
    mf_reports {
        int id PK
        int user_id
        text source "morningstar; unique with scheme_key, report_date"
        text scheme_key
        text scheme
        text isin
        text report_date
        text month "YYYY-MM of its portfolio date"
        text data "JSON as parsed"
        text file_name
        text sha256
        text imported_at
        blob pdf "the report itself, shown in MF Analysis"
    }
```

![Data model](data-model.jpg)

Notes on the model:
- **Effective dating.** A month uses the latest `category_targets` / `budget_history` row whose `from_month` is on or before that month, so changing a target or salary never rewrites earlier months. Budget cap = `income − savings_amount`.
- **Category lifecycle.** A category is shown in a month if that month is within `start_month`–`end_month` *or* it already has expenses that month, so totals always agree with the data. The same rules apply to sub-categories.
- **Sub-categories** are a reporting label: a category's total always equals the sum of its sub-categories plus *Unassigned*.
- **Portfolio tables.** `holdings` is the current position; `transactions` is the dated history (it may update a holding but deleting a row never reverses it); `sip_log` guarantees a SIP is applied once per month; `portfolio_snapshots` holds one net-worth row per user per day; `holding_snapshots` is the same idea per holding, so an individual stock or fund's value can be charted over time even though `holdings.cmp`/`qty` are overwritten in place on every price refresh; `price_history` / `price_runs` log the daily price job; `portfolio_goals` and `portfolio_plan` (key/value JSON) hold goals, target allocation and return assumptions. A goal's `kind` decides how it is paid: **large** goals are withdrawn from the corpus in the Monte Carlo (`portfolio.simulate`); **small** goals and **recurring** expenses (school fees, the trip home) are paid from one steady monthly set-aside that `portfolio.commitments` works out over the next 24 months, along with the one-time top-up, the share of the monthly surplus it uses and, for a recurring expense linked to a category, what was actually spent in its last cycle. None of that is stored. `holding_groups` is linked to `holdings.grp` by name, not by id.
- **Stock ledger.** `equity_trades` holds every broker trade, keyed by a fingerprint so a re-uploaded or duplicated tradebook adds nothing; `client_id` stops one account's file being imported under another. Positions are never stored: `equity.py` replays trades with `equity_events` (corporate actions, plus a few built into the code for what Yahoo misses) into FIFO lots per account. `equity_dividends` rows from a broker statement replace that account's period on re-import; rows fetched from Yahoo (`dividend_agent.py`) only fill dates after the statements and are replaced when a later statement arrives. The share count on every statement ex-date and on the latest `broker_holdings` statement is checked against the replay (the Audit tab). `equity_audit` records what each import, refresh and event edit changed, so the broker files can be deleted afterwards.
- **Exposure and tags.** `grp` is where a holding sits (and what targets are set against); `exposure` is one of Equity / Gold / Debt / Cash and is what the money is really invested in, so the exposure shares always add up to 100%. `tags` are optional extra labels (sector, theme) that may overlap; a holding also shows under a group filter named like one of its tags. The target Equity / Gold / Debt ratio, expected returns and time windows live in `portfolio_plan` under `mix_targets`, `mix_returns`, `mix_reach_years` and `mix_years`; Cash counts as Debt there. Older `exposure_targets` are still read as a fallback.
- **Forecasts** are computed on request from `expenses`; nothing is stored (see `plan/spendlens-forecasting-ml-plan.md` for the planned `forecasts` tables).
- **Billing accounts.** A card number and a bill are different things. `card_accounts` groups the cards that share one bill: an ICICI account list names several card numbers, and payments are posted under one yet settle all, so the due date, the payments and the *when to pay* answer belong to the account while spend and rewards belong to the card. Each card number is its own `cards` row. Which numbers are one *physical* card (a re-issue under a new number) is not stored: it is inferred from the dates on every read (`cards.lineage`), so it does not depend on upload order.
- **Credit cards.** `cards` holds the card and its terms; `card_statements` one row per billing cycle, keyed by `period_to`, carrying both the cashback the statement *paid* (`cashback_reported`) and what the rules say it *should* have paid (`cashback_calc`) — the difference is shown on the dashboard rather than hidden. `card_txns` holds the transactions, de-duplicated by `row_hash` so re-importing an overlapping statement adds nothing, with `cls` (a reward class from the card's profile) deciding the rate. `card_merchant_rules` are your corrections to that classification; saving one re-applies the engine to all of history. `kind` separates what was *spent* from what the bank *billed*: net spend is purchases minus refunds plus EMI instalments, while interest, tax and fees are costs, not spend. **Card spend is not written into `expenses`**: the statements cover months that already have hand-entered expenses, so merging them would double count. Linking the two is a later, explicit step.
- **Card perks.** `card_perks` is a card's benefits written down by hand (`spendlens/card_perks.py`): rewards, milestones, lounge access, fees, exclusions and caps, each with an optional yearly value (`value_yr`) and a `source`. A card is seeded once from its scheme's published terms (`cards.perks_seeded` guards the seed) with every row starting unconfirmed (`checked = 0`); after you confirm or edit one it is `checked = 1` and the list is yours. These rows are documentation only — nothing in the reward maths reads them. `cards.color` and `cards.sort_order` are display-only: a fixed colour per card (empty = auto-assigned) and the drag position on the Cards page.
- **Reminder calendar.** `reminder_categories` and `reminders` hold what you set up (rent, EMI, school fees...); `reminder_settings` holds the evening "log expenses" nudge. Card statement/due dates (`cards.statement_day`, `due_day`, or statement day + `grace_days` when no due day is set, shown as an estimate) and SIP dates (`holdings.sip_day`) are **not stored**: they are read from `cards` and `holdings` each time, so editing a card or SIP changes the calendar and the feed immediately. A reminder's state is worked out per month: *done* when an expense exists in its linked category (and sub-category) that month, *missing* when the date has passed without one, *up* while it is still ahead. Suggestions (`GET /reminders/suggestions`) are computed from `expenses` and never stored; keeping one creates a normal reminder with `source_key` set so it is not offered twice. `GET /calendar.ics` renders everything as an iCalendar feed (all-day recurring events plus a daily floating-time nudge). **Holidays and vacations.** India and US public holidays are **not stored**: the `holidays` package (pinned in `spendlens/requirements.txt`) supplies them per month and they come back in `GET /reminders/calendar` as `holidays`. `vacations` are yours: coloured, inclusive date ranges, returned unclipped in every month they overlap, and included in the feed as all-day events (exclusive `DTEND`) under the `vacation` type. Holidays are not in the feed. **Drag to move.** `reminder_overrides` holds one month's occurrence of a reminder moved to another day (`PUT /reminders/{id}/move` with `scope=month`); `scope=all` changes `reminders.day` instead. The feed emits a moved occurrence as an extra VEVENT with the series UID and a `RECURRENCE-ID`. **Day trackers.** `trackers` (gym day, office day...) and the days you tick (`tracker_days`) are stored; their KPIs are **not**: `GET /reminders/calendar` works them out per month. Weeks are Monday rows clipped to the month, a week's goal is the weekly target scaled to that week's scheduled days (the tracker's weekdays, minus vacation days and public holidays it pauses on), and `tracker_cost_links` names the expense categories whose spending is averaged on ticked vs unticked days. `bill_reminder_id` turns a bill (a gym membership) into a cost per visit. Trackers are not in the feed.
- **Two databases.** Both hold the same tables. The main one takes every save; the other is refreshed from it about 10 s after the last save, every 15 minutes and at shutdown, always as a complete copy checked table by table (`spendlens/db/replicate.py`, `db/mirror.py`): PostgreSQL → a freshly built SQLite file swapped in atomically, or SQLite → PostgreSQL in one transaction. Admin › Database switches which one is main (`POST /database/switch`), copying everything into it first; the choice is stored in `spendlens/database-mode.json`, not in either database. If PostgreSQL is the main database and can't be reached, the app reads the SQLite copy read-only until it is back. Housekeeping files next to the SQLite file, none of them data: `spendlens_v2.db.mirror.json` and `spendlens_v2.db.sync.json` (time and outcome of the last copy each way), `.spendlens_v2.db.template.db` (the empty schema each refresh starts from) and `spendlens_v2.pre-postgres.bak` (the SQLite database as it was before PostgreSQL took over). `holdings.sip_reminder` only hides a SIP from the reminders; Holdings still applies it.
- **Migrations.** Alembic owns the schema (`alembic/`, `spendlens/db/models/`). `app.py` runs `upgrade head` through `db/migrate.py`'s `prepare_database()`; on an empty database (SQLite or PostgreSQL) the baseline revision creates every table that predates Alembic plus the starter data in `spendlens/db/seed.py`. `schema_migrations` is the record of the older numbered steps in `MIGRATIONS` (`database.py`): a database built by Alembic lists all of them as done, and they only ever run for an old SQLite file from before Alembic, which `database.init_db()` brings up to date before Alembic adopts it. The same schema runs on PostgreSQL (`DATABASE_URL`); there `categories.target_pct` and `category_targets.target_pct` are double precision, since those INTEGER-declared SQLite columns hold fractional targets. See the README's "Tests and migrations" section.
- **Users and access.** `users` holds the people who can sign in (bcrypt `password_hash`, `role` admin / user, `is_active`). A sign-in is an `auth_sessions` row keyed by the sha256 of the `sl_session` cookie, so the database never holds a usable token; it lasts 30 days and is deleted on sign-out, on an admin password reset or deactivation, and (except for the session that made the change) on a password change. `module_grants` has one row per module a user has (expense, holdings, ledger, cards; admins have all of them without rows); `access_requests` is the queue a user raises for a locked module and an admin approves or rejects (approving adds the grant in the same transaction). The first admin is created on first start as `users.id = 1`, who owns all data from before multi-user support.
- **`user_id` and scoping.** Every user-owned table carries `user_id` (shown in the diagram). Routes never filter by it themselves: `spendlens/db/scope.py` adds `user_id = <signed-in user>` to every ORM SELECT / UPDATE / DELETE on those tables and stamps it on every new row, so a route cannot reach another user's data by forgetting a filter or guessing an id. Raw SQL is not covered: `cards.py` writes `user_id = :uid` itself. Child tables without a `user_id` (`category_targets`, `tracker_days`, `tracker_cost_links`, `reminder_overrides`, `holding_snapshots`, `price_history`, `card_statements`, `card_txns`, `card_perks`) are only reached through a parent the user owns. Unique keys that used to be global are per user (`(user_id, from_month)` on `budget_history`, `(user_id, key)` on `portfolio_plan`, holding group names per user). `tests/test_isolation.py` checks that one user can't see another's rows. `app_prefs` is a key/value store whose keys carry the user id (`holding_columns:<id>`; user 1 keeps the plain `holding_columns`).
- **MF Analysis.** Filled by `spendlens/import_mf.py` from the validated JSON that `/mf-factsheets` writes; the factsheets themselves are not kept. `mf_sources` is one imported file for one month (factsheet or portfolio disclosure) with its `sha256`, which is what `--delete-imported` checks before deleting a source file. `mf_fund_months` is one fund in one month exactly as the factsheet printed it (AUM, TER, risk ratios, returns vs benchmark, cap mix, cash, debt metrics, managers with their start dates): a figure that isn't printed stays NULL, never guessed. Its identity across months is `scheme_key` (normalised scheme name + plan, so several folios of one fund are one fund), unique per user and month; re-importing a file replaces what it imported. `mf_holdings` is that fund's portfolio that month (a portfolio disclosure, imported after the factsheet, replaces the factsheet's top-10 list with the full holdings and share counts). `mf_reports` keeps Morningstar fund reports to cross-check the AMC's figures, with the parsed `data` (JSON) and the PDF itself (`pdf`, loaded only when the report is opened). Scorecard, buying trend, overlap and anomalies are computed on read (`spendlens/mf.py`), not stored.
- A legacy `settings` table (not in the diagram) exists only so old databases can be migrated into `budget_history`; it is keyed on `user_id`. The unused tables `rebalance_targets` and `price_alerts` were dropped by migration 2; nothing ever read them. (An unrelated, unused early `users` table went with them; today's `users` table comes from Alembic revision `f7b9d2e5a0c4`.)
