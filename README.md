# SpendLens

Personal expense and portfolio tracker (₹, lakh/crore formatting). FastAPI backend on PostgreSQL with a verified
SQLite copy (or SQLite alone), React + Vite frontend.

- **Expense** – month grid per category/day with keyboard-first entry, one *Add expense* dialog (single day or a range like `5-12`), sub-categories you can type into directly, month navigation.
- **Calendar** (Expense › Calendar) – reminders for bills and EMIs (suggested from your history), card statement and due dates, SIPs, India and US public holidays, vacations, tick-box day trackers (gym, office...) with KPIs, drag-and-drop to move a reminder, and an `.ics` feed for phone calendars.
- **Holdings** – grouped portfolio (net worth, gain, allocation, insights, sortable by value, invested, gain ₹ or gain %), click a row to edit, CSV export.
- **MF Analysis** (preview) – your mutual funds judged month by month from AMC factsheets: scorecard (returns vs benchmark, rolling consistency, Sharpe / Sortino, downside and upside capture, drawdown, costs, concentration), trends, anomalies, overlap between your funds, factsheet coverage and a guide to every parameter. The fund list is your MF holdings; the metrics are sample data until factsheet import (`factsheets/YYYY-MM/<AMC>.pdf`) is built.
- **Ledger** – the stock ledger built from broker files (Zerodha Console tradebooks, dividend statements and the holdings statement) for one or more demat accounts: dividends per stock by quarter and financial year, realised gains (FIFO), XIRR per stock and overall (with and without dividends), held and exited stocks, corporate actions, and an audit that reconciles every share count. A Refresh button fetches prices, splits and newer dividends from Yahoo.
- **Dashboard** – Expense dashboard (spend vs budget and pace, projected month-end, where it went with targets and sub-categories, 12-month trend, forecast) and Portfolio dashboard (KPIs, goal odds with a simulated range, allocation vs target, risk, performers, history).
- **Cards** – credit-card cashback dashboard: statement import, what each card earned vs what it could have, merchant breakdown, fee-waiver and utilisation meters, and the spend worth moving. See [CREDIT_CARDS.md](CREDIT_CARDS.md).
- **Admin** – categories and sub-categories, targets and budget, reminders, trackers and vacations, holding groups, goals and target allocation, daily prices, and **Database** (which database is the main one, and the switch between PostgreSQL and SQLite).

Where this is going: [ROADMAP.md](ROADMAP.md) (phases, and the redundancies to remove
first), [CREDIT_CARDS.md](CREDIT_CARDS.md) (the planned credit-card profit module) and
[spendlens-forecasting-ml-plan.md](plan/spendlens-forecasting-ml-plan.md) (forecasting / ML, which is Phase 5 of the roadmap).

## Project structure

```
ExpenseTrack/
├── README.md                    this file
├── ROADMAP.md                   product roadmap: phases, redundancy register
├── CREDIT_CARDS.md              planned credit-card profit module
├── plan/                                             forecasting / ML roadmap (Phase A done, B and C planned)
├── package.json                 pnpm workspace scripts (dev, build, typecheck)
├── pnpm-workspace.yaml          workspace + esbuild build-script allowance
├── alembic.ini, alembic/        schema migrations (see "Tests and migrations" below)
├── screenshot/                  source Excel sheet used to import holdings
├── spendlens/                   BACKEND (Python)
│   ├── app.py                   FastAPI app, port 5000: reads .env.local, prepares the database
│   │                            (db/failover.startup), mounts /spendlens/api, serves the built UI
│   ├── database.py              month helpers, categories_for_month, budget_for_month; init_db() only
│   │                            adopts a pre-Alembic SQLite file
│   ├── subcategories.py         sub-category seed, note → sub-category matching rules
│   ├── forecast.py              baseline forecasting + backtest (GET /forecast)
│   ├── portfolio.py             portfolio KPIs, snapshots, XIRR, goal Monte Carlo
│   ├── prices.py                daily equity (Yahoo) and MF (AMFI) prices, scheduler
│   ├── ledger.py                dated holding flows (SIPs) for the Holdings XIRR KPI
│   ├── equity.py                stock ledger: replay, dividends, XIRR, reconciliation
│   ├── equity_import.py         Zerodha tradebook / dividend / holdings file parsing
│   ├── import_broker.py         command line: import a folder of broker files, then refresh
│   ├── dividend_agent.py        Refresh: Yahoo prices, splits and dividends, cross-checked
│   ├── sip.py, accrual.py       SIP application, FD/RD auto valuation
│   ├── cards.py                 card import (SBI parser, PARSERS registry, Claude fallback), profiles, earn engine, dashboard
│   ├── cards_icici.py, cards_bob.py, cards_hdfc.py, cards_amex.py   statement parsers per bank
│   ├── card_float.py            when to pay: billing cycle, payment matching, float cost
│   ├── card_advisor.py          which card for what: best card per spend kind, cost of the wrong one
│   ├── card_perks.py            card benefits (rewards, milestones, lounge, fees) — seed, read, edit
│   ├── requirements.txt
│   ├── db/                      SQLAlchemy layer
│   │   ├── engine.py            engine + SessionLocal; DATABASE_URL picks PostgreSQL, else the SQLite file
│   │   ├── base.py              declarative Base, row_dict
│   │   ├── migrate.py           prepare_database(): Alembic upgrade head (adopts pre-Alembic SQLite files)
│   │   ├── seed.py, ddl.py      starter data and dialect-neutral helpers used by the migrations
│   │   ├── replicate.py         copies every table between two databases and verifies the copy
│   │   ├── mirror.py            keeps the copy fresh: PostgreSQL → SQLite file, or SQLite → PostgreSQL
│   │   ├── failover.py          which database is main, the switch, the read-only fallback, API guard
│   │   └── models/              expense, portfolio, cards, reminders and trackers tables
│   ├── routes/
│   │   ├── api.py               combines the routers below into the one app.py includes
│   │   ├── expense_routes.py    categories, budget, sub-categories, expenses, dashboard, forecast
│   │   ├── investing_routes.py  holdings, goals, asset mix, daily prices
│   │   ├── card_routes.py       cards, statement import, merchant rules, perks, advice
│   │   ├── reminder_routes.py   reminders, calendar month, holidays, vacations, .ics feed
│   │   ├── tracker_routes.py    day trackers, ticks and their KPIs
│   │   └── status_routes.py     GET /status, POST /database/switch
│   ├── tools/copy_to_postgres.py  one-off: copy a SQLite file into PostgreSQL and verify
│   └── spendlens_v2.db          the SQLite database (main or copy; back it up)
├── run-api.ps1                  starts the API with DATABASE_URL from .env.local
├── .env.local                   (git-ignored) DATABASE_URL / TEST_DATABASE_URL for PostgreSQL
└── artifacts/spendlens/         FRONTEND (React 19 + Vite + TypeScript)
    ├── index.html, vite.config.ts (proxy /spendlens/api → :5000), tsconfig.json
    └── src/
        ├── main.tsx, App.tsx    entry and top-bar navigation (Expense / Holdings / Ledger / Cards / Dashboard / ⚙ Admin)
        ├── api.ts               typed API client
        ├── theme.ts, months.ts, index.css
        └── components/
            ├── Expense.tsx          month grid, quick entry, expandable sub-category rows
            ├── ExpenseDialogs.tsx   cell editor (lines) and Add expense dialog
            ├── MonthPicker.tsx      ‹ month, year (years with data) ›
            ├── Dashboard.tsx        Expense + Portfolio dashboards
            ├── Holdings.tsx
            ├── Cards.tsx            credit-card cashback dashboard + statement import
            ├── Ledger.tsx           stock ledger: dividends, XIRR, audit, corporate actions
            ├── PortfolioDashboard.tsx  KPIs, goals, allocation, risk, history
            ├── Admin.tsx            Admin shell and tool registry (ADMIN_TOOLS)
            ├── ReminderCalendar.tsx  the Calendar view: reminders, holidays, vacations, trackers, KPIs
            ├── DatabaseBanner.tsx   'read-only copy' banner while PostgreSQL is down
            ├── admin/               Categories.tsx, Reminders.tsx, Database.tsx, Targets.tsx, HoldingGroups.tsx, PortfolioPlan.tsx, Prices.tsx, ...
            └── ui.tsx               Card, Modal, Field, Doughnut, buttons, inputs
```

## Architecture

```mermaid
flowchart LR
    UI["React UI<br/>artifacts/spendlens"] -- "/spendlens/api (JSON)" --> API["FastAPI<br/>routes/ (6 routers)"]
    API --> GUARD["db/failover.py<br/>main database, switch,<br/>read-only fallback"]
    GUARD --> PG[("PostgreSQL<br/>main database")]
    GUARD -. "read-only while<br/>PostgreSQL is down" .-> LITE[("SQLite<br/>spendlens_v2.db")]
    PG -- "db/mirror.py: verified copy<br/>~10 s after saves, every 15 min" --> LITE
    API --> F["forecast.py"]
    API --> P["portfolio.py / ledger.py<br/>sip.py / accrual.py"]
    API --> PX["prices.py<br/>daily price refresh"]
    API --> CARDS["cards.py + parsers<br/>card_float / advisor / perks"]
    API --> REM["reminder_routes / tracker_routes<br/>calendar, .ics feed, KPIs"]
    REM --> HOL["holidays package<br/>India + US"]
    CARDS -. "unrecognised format<br/>(opt-in)" .-> CLAUDE["Anthropic API<br/>(ANTHROPIC_API_KEY)"]
    SCH(["background scheduler<br/>every 15 min"]) --> PX
    PX -- "NSE closes" --> Y["Yahoo Finance"]
    PX -- "NAVAll.txt" --> A["AMFI"]
    API -. "serves dist/public" .-> UI
```

The roles of the two databases can be swapped from Settings › Database; the copy then runs the other way (SQLite →
PostgreSQL). Without `DATABASE_URL` there is only the SQLite file and none of the failover machinery runs.

### Detailed architecture

The same system, zoomed in: every page, every endpoint group and every backend module, grouped into layers so each
box only needs the one next to it to make sense.

```mermaid
flowchart TB
    subgraph FE["FRONTEND — React 19 + Vite (artifacts/spendlens)"]
        direction LR
        PAGE_E["Expense<br/>Sheet + Calendar"]
        PAGE_H["Holdings"]
        PAGE_L["Ledger"]
        PAGE_C["Cards"]
        PAGE_D["Dashboard"]
        PAGE_A["Admin<br/>ADMIN_TOOLS registry,<br/>Database switch"]
        BANNER["DatabaseBanner<br/>polls /status"]
        API_TS["api.ts<br/>typed client"]
        PAGE_E & PAGE_H & PAGE_L & PAGE_C & PAGE_D & PAGE_A & BANNER --> API_TS
    end

    API_TS -- "/spendlens/api/* (JSON, same origin)" --> MW

    subgraph BE["BACKEND — FastAPI (spendlens/)"]
        MW["failover middleware<br/>503 while switching or read-only,<br/>lost-connection detection"]
        ROUTER["routes/api.py<br/>combines the 6 routers"]
        MW --> ROUTER

        subgraph EXP["Expense & budget — expense_routes.py"]
            direction LR
            DBPY["database.py<br/>month helpers"]
            SUBC["subcategories.py<br/>note → sub-category rules"]
            FCST["forecast.py"]
        end
        subgraph PORT["Portfolio — investing_routes.py"]
            direction LR
            PF["portfolio.py"]
            LED["ledger.py"]
            SIPM["sip.py / accrual.py"]
            PRX["prices.py"]
        end
        subgraph CARD["Credit cards — card_routes.py"]
            direction LR
            CPY["cards.py + parsers"]
            CFLOAT["card_float.py"]
            CADV2["card_advisor.py"]
            CPERK2["card_perks.py"]
        end
        subgraph CAL["Calendar — reminder_routes.py, tracker_routes.py"]
            direction LR
            REMS["reminders, suggestions,<br/>holidays, vacations, .ics"]
            TRK["trackers, ticks, KPIs"]
        end
        STAT["status_routes.py<br/>/status, /database/switch"]

        ROUTER --> EXP & PORT & CARD & CAL & STAT

        subgraph DBL["Database layer — spendlens/db/"]
            direction LR
            SESS["engine.py<br/>SessionLocal"]
            FO["failover.py<br/>main db, switch, fallback"]
            MIR["mirror.py<br/>scheduled copy"]
            REP["replicate.py<br/>copy + checksum verify"]
            MIG["migrate.py + Alembic<br/>schema on startup"]
            FO --> SESS
            FO --> MIR --> REP
        end

        EXP & PORT & CARD & CAL --> SESS
        STAT --> FO
        SCHED(["scheduler, every 15 min"]) --> PRX
    end

    SESS --> PG[("PostgreSQL<br/>main")]
    SESS -. "fallback / after a switch" .-> LITE[("SQLite<br/>spendlens_v2.db")]
    REP -- "copy, both directions" --> PG & LITE
    PRX -- "NSE closes" --> YF["Yahoo Finance"]
    PRX -- "NAVAll.txt" --> AMFI["AMFI"]
    CPY -. "unrecognised PDF, opt-in" .-> CLAUDE["Anthropic API<br/>reply type-checked + totals re-checked"]
    ROUTER -. "serves artifacts/spendlens/dist/public" .-> FE
```

Reading it top to bottom: the **frontend** pages all go through one typed client (`api.ts`). Every request first
passes the **failover middleware**, which refuses writes with a clear 503 while the app is on the read-only copy or
in the middle of a database switch. `routes/api.py` then hands it to one of six routers (**expense & budget**,
**portfolio**, **credit cards**, **calendar** (reminders and trackers) and **status**), each a handful of plain
Python modules with one job apiece. Every route gets a SQLAlchemy session from `SessionLocal`, which
`db/failover.py` points at whichever database is the main one: PostgreSQL normally, the SQLite file after a switch,
or the SQLite file read-only while PostgreSQL is unreachable. `db/mirror.py` keeps the other database a verified
copy of the main one, using `db/replicate.py`. On startup `app.py` runs Alembic's migrations (`db/migrate.py`), so a
brand-new database and the live ones always end up in the identical shape. The only things that leave your machine
are the price refresh (Yahoo Finance, AMFI, both free, no key) and, only if you opt in, an unrecognised card
statement going to the Anthropic API.

## API documentation (Swagger)

FastAPI publishes the whole API from the code, so the docs are always current. With the server running:

| What | URL |
|---|---|
| Swagger UI: browse every endpoint and call it from the browser | http://localhost:5000/docs |
| ReDoc: the same, as a readable reference | http://localhost:5000/redoc |
| OpenAPI spec (JSON), for Postman, Insomnia or code generators | http://localhost:5000/openapi.json |

In Swagger, open a group (expense, portfolio, cards, reminders, trackers, status), pick an endpoint, press
**Try it out**, fill in the parameters and press **Execute**: the request runs against your real data, so a
`POST`/`PUT`/`DELETE` there changes it. Every endpoint lives under `/spendlens/api/...`. A few to start with:

- `GET /spendlens/api/healthz` – is the server up
- `GET /spendlens/api/status` – which database is the main one, when the copy was last refreshed, read-only or not
- `GET /spendlens/api/expenses/monthly-grid?month=2026-10` – the expense sheet for a month
- `GET /spendlens/api/reminders/calendar?month=2026-10` – reminders, holidays, vacations and tracker KPIs for a month
- `GET /spendlens/api/calendar.ics` – the calendar feed
- `POST /spendlens/api/database/switch` with `{"to": "sqlite"}` or `{"to": "postgresql"}` – change the main database

The docs are at the server root (`/docs`), not under `/spendlens/api`; any other path, such as
`/spendlens/api-docs`, just opens the app.

## Data model

Tables, relationships and modelling notes are in [DATA_MODEL.md](DATA_MODEL.md). In short:

- **Expense & budget**: `categories` → `subcategories` (+ `subcategory_rules` that label expense notes) → `expenses`; `category_targets` and `budget_history` are effective-dated by month.
- **Portfolio**: `holdings` with `transactions`, `sip_log`, `price_history`, daily `portfolio_snapshots` / `holding_snapshots`, `portfolio_goals` and `portfolio_plan`.
- **Credit cards**: `card_accounts` → `cards` → `card_statements` → `card_txns`, plus `card_merchant_rules` and `card_perks`.
- **Calendar**: `reminder_categories` → `reminders` (+ `reminder_overrides` for one-month moves), `reminder_settings`, `vacations`, `trackers` → `tracker_days` / `tracker_cost_links`. Card dates, SIP dates, holidays and tracker KPIs are computed, not stored.
- **Two databases**: the same tables live in PostgreSQL and in `spendlens/spendlens_v2.db`; one is the main database and the other a verified copy of it. Which is main is kept in `spendlens/database-mode.json`, outside both.

## Prerequisites

- Python 3.10+
- Node.js 20+ and [pnpm](https://pnpm.io) (`npm i -g pnpm`)

## First-time setup

Run from the project root (the folder containing this README), in PowerShell:

```powershell
# backend
python -m venv venv_expense
.\venv_expense\Scripts\activate
pip install -r spendlens\requirements.txt

# frontend
pnpm install
```

## Run the application

Run everything from the project root (the folder containing this README) in PowerShell. There are two ways to run it; pick one.

### Option A – single server (simplest, everyday use)

The backend serves both the API and the built UI on one port.

```powershell
.\venv_expense\Scripts\activate
pnpm build                # only needed the first time and after frontend changes
python spendlens\app.py
```

Open **http://localhost:5000**. `app.py` reads `DATABASE_URL` from `.env.local` when that file exists, so this runs on PostgreSQL (with the SQLite copy); without it, on the SQLite file, which it creates and seeds on first start. Health check: http://localhost:5000/spendlens/api/healthz should return `{"status":"ok"}`; http://localhost:5000/spendlens/api/status says which database is in use. All endpoints: http://localhost:5000/docs (see *API documentation* above).

### Option B – development (backend + frontend with hot reload)

Use two terminals; both must stay open.

```powershell
# Terminal 1 – backend (API on :5000)
.\venv_expense\Scripts\activate
python spendlens\app.py

# Terminal 2 – frontend (Vite dev server on :3000)
pnpm dev
```

Open **http://localhost:3000**; it proxies `/spendlens/api` to the backend on port 5000. If the backend is not running every page shows `Request failed (500)`.

### Sign-in, password reset and network access

- **First start.** With no users yet, the backend creates the admin. Set `SPENDLENS_ADMIN_EMAIL` /
  `SPENDLENS_ADMIN_PASSWORD` to choose the login; otherwise the email is `admin@spendlens.local` and a random password
  is written to `spendlens\first-admin-password.txt` (git-ignored, never printed). Sign in, change the password and
  delete the file.
- **Forgot password.** The sign-in page's *Forgot password?* works only in a browser on the computer running
  SpendLens, and asks for the **reset code** the backend prints when it starts
  (`[spendlens] Password reset code ...: ABCD-EFGH`). A used code is replaced by a new one, printed in the same window.
  Without the console: `python spendlens\reset_password.py`. An admin can also reset anyone in Admin › Users.
- **Throttling.** Five wrong passwords for one account (or 20 across accounts) from one address lock sign-in for
  15 minutes (HTTP 429); five wrong reset codes lock the reset form the same way. Restarting the backend clears it.
- **Changing your password** signs you out everywhere else; the session you changed it from stays signed in.
- **This computer only, by default.** The backend listens on `127.0.0.1` and the Vite dev server on `localhost`. To
  use SpendLens from your phone or another machine, set `SPENDLENS_HOST=0.0.0.0` (backend) or
  `VITE_HOST=0.0.0.0` (`pnpm dev`), and put HTTPS in front of it, for example Tailscale (`tailscale serve 5000`)
  or Caddy (`caddy reverse-proxy --from spendlens.example --to localhost:5000`). Plain HTTP on a network sends your
  password and session cookie readable by anyone on it. Behind HTTPS the cookie is marked `Secure` automatically;
  `SPENDLENS_SECURE_COOKIE=1` forces it.
- **Other protections.** A state-changing API call whose `Origin` is another site is refused (403), and pages get a
  Content-Security-Policy and anti-framing headers (`spendlens/security.py`). Swagger (`/docs`) is on while the
  backend listens on this computer only; with `SPENDLENS_HOST` set to a network address it is off unless
  `SPENDLENS_DOCS=1`.

Notes:
- Run the tests with `pnpm run test` (or `python -m pytest`); `pnpm run check` does
  typecheck + build + tests. See *Tests and migrations* below.
- Restart the backend after any Python change (stop with Ctrl+C, run it again). Frontend changes reload by themselves in Option B; in Option A run `pnpm build` and hard-refresh (Ctrl+F5).
- The backend also runs the daily price refresh in the background, so keep it running (or just open it now and then; missed runs are caught up at start-up).
- `PORT` changes the backend port (`$env:PORT = 5001`), but then update the proxy in `artifacts/spendlens/vite.config.ts`.
- Check types with `pnpm run typecheck`.

URL params: `?page=expense|holdings|ledger|cards|dashboard|admin`, `&tab=portfolio`, `&tool=categories|subcategories|targets|holding-groups|portfolio-plan|prices`.

### PostgreSQL as the main database, with a SQLite mirror

With `DATABASE_URL` pointing at PostgreSQL the app uses it as the main database. `python spendlens\app.py` (and
`.\run-api.ps1`) read it from the git-ignored `.env.local` in the project root; without that file (or with
`DATABASE_URL` unset) the app runs on SQLite exactly as before, and none of the following applies.

- **Switching the main database.** Settings › General › Database shows which one is the main database (it takes
  every save) and when the other, the copy, was last updated. *Make SQLite / PostgreSQL the main database* pauses
  saving for a few seconds, copies everything into the new main database and checks it table by table, then swaps
  the roles: from then on the copy is kept up to date in the other direction. The choice is remembered in
  `spendlens/database-mode.json`, so a restart keeps it. While PostgreSQL is down you can switch to SQLite to keep
  saving; switching back copies everything saved meanwhile into PostgreSQL. (Only the main database takes saves, so
  the two never have to be merged.)

- **Mirror.** The app keeps a complete SQLite copy of PostgreSQL at `spendlens/spendlens_v2.db` (the file the app
  used before; change it with `SPENDLENS_MIRROR`). It is rebuilt about 10 s after the last save, every 15 minutes,
  and when the server stops with Ctrl+C. Each refresh builds a new file, verifies it table by table and only then
  replaces the old one, so the mirror is always a whole, checked copy. The first refresh keeps the file that was
  there before as `spendlens_v2.pre-postgres.bak`. When and whether the last refresh worked is in
  `spendlens_v2.db.mirror.json`, and in `GET /spendlens/api/status`.
- **Read-only fallback.** If PostgreSQL can't be reached (at start-up within 3 s, or later: the app checks every 30 s
  and on any lost connection), the app switches to the mirror, read-only. Every page shows a banner saying so;
  viewing works, saving is refused with a message, and background jobs that write (due SIPs, snapshots, price
  refreshes) wait. When PostgreSQL answers again the app switches back by itself and refreshes the mirror. Anything
  you could not save during the outage has to be entered again: nothing is queued.
- **Back to SQLite for good.** Stop the server, rename `.env.local`, start it again: it then uses the mirror file as
  its database. Copying SQLite into PostgreSQL again: `python spendlens\tools\copy_to_postgres.py --source <file> --target <url>`.

### Stop the server

Press Ctrl+C in its terminal (with PostgreSQL this also takes a last mirror). If it was started hidden or the terminal is gone, free the port with:

```powershell
Get-NetTCPConnection -LocalPort 5000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

## Troubleshooting

- **`Request failed (500)` in the UI** – the backend is not running on port 5000 (the Vite proxy returns 500 when it can't connect). Start it as above. Port 8000 is not used by this app.
- **`Address already in use` / `[Errno 10048]`** – an earlier copy of the backend is still running on port 5000 (often a hidden or forgotten terminal). Stop it with the command under *Stop the server*, then start again.
- **Blank page after `pnpm build`** – rebuild, then restart the backend so it picks up `dist/public`.
- **Missing new data fields or odd behaviour after code changes** – a stale backend is still running; stop it and start it again.

## Tests and migrations

```powershell
.\venv_expense\Scripts\activate
pip install -r spendlens\requirements-dev.txt    # first time only
python -m pytest                                 # or: pnpm run test
```

**The suite never touches your data.** `tests/conftest.py` sets `SPENDLENS_DB` to a
throwaway file before anything is imported, and builds it with Alembic exactly as
`app.py` does. Tests that need realistic data get a *copy* of `spendlens_v2.db` and are
skipped if the file is not there.

**Running the suite on PostgreSQL.** Point `TEST_DATABASE_URL` at an empty database kept
for tests (its name must end in `_test`; it is wiped at the start of every run), or put
the URL in the git-ignored `.env.local` and set `SPENDLENS_TEST_PG=1`:

```powershell
$env:SPENDLENS_TEST_PG = "1"; python -m pytest; Remove-Item Env:SPENDLENS_TEST_PG
# or: $env:TEST_DATABASE_URL = "postgresql+psycopg://user:pass@localhost:5433/spendlens_test"
```

CI runs the suite twice: on SQLite, and on a PostgreSQL 16 service container. Tests about
the SQLite file itself (the legacy migration chain, copies of the real file) skip on
PostgreSQL.

- `tests/test_migrations.py` – the legacy migration chain is applied once, is idempotent,
  backs up first, and does not change your expense data.
- `tests/test_api_shape.py` – every read endpoint answers 200 and still carries the keys
  the UI reads. When a key here changes, `src/api.ts` changes with it.
- `tests/test_mix_math.py` – the SIP-mix engine's invariants: the mix equals the target
  at the reach month, the forecast matches a brute-force loop, no SIP share is ever
  negative, and an unreachable target is reported rather than faked.

**Alembic owns the schema.** `app.py` calls `spendlens/db/migrate.py`'s
`prepare_database()`, which runs `alembic upgrade head`. On an empty database (a new
SQLite file, or PostgreSQL) the baseline revision `218d401380ff` creates every table that
predates Alembic and the starter data (`spendlens/db/seed.py`: categories, a sample month,
sub-category rules, the first card); later revisions build on that. On your existing
SQLite file it changes nothing. The only other path is an old SQLite file from before
Alembic (tables but no `alembic_version`): `database.init_db()` first brings it up to the
last hand-rolled schema (the numbered `MIGRATIONS` in `database.py`), then Alembic adopts
it. That legacy path is the only code that still uses the `sqlite3` library.

The app uses SQLite (`spendlens/spendlens_v2.db`) unless `DATABASE_URL` is set, for
example `postgresql+psycopg://user:pass@localhost:5433/spendlens`. Write migrations so
they run on both: use `db/ddl.py`'s helpers for timestamp defaults (`now_text`) and to
move PostgreSQL's id sequences after explicit-id inserts, `sa.true()` / `sa.false()` for
boolean defaults, and guard work an earlier revision or the baseline may already have
done (see `459d2bc3ff86` and `7fa60c624af4`).

To add a schema change: write a SQLAlchemy model (or extend one) in
`spendlens/db/models/`, then from the repo root:

```powershell
.\venv_expense\Scripts\python -m alembic revision -m "describe the change"
# edit the generated file in alembic/versions/ — review autogenerate, don't trust it blindly
.\venv_expense\Scripts\python -m alembic upgrade head
```

Test the migration on a *scratch copy* of `spendlens_v2.db` first — upgrade, downgrade,
upgrade again — and on the PostgreSQL test database, before ever running it against the
real file.

## Cards (credit cards)

**Admin → Cards** lists every card. Rename a card, or mark it *closed* when you no longer use it: its data is kept in
full (cards are never deleted), it is greyed out, and it leaves pay dates and recommendations. Reopen it any time.
Statements also import from American Express `.xlsx` exports and HDFC Tata Neu PDFs.

**Benefits** are written down per card (Admin → Cards → Benefits, and on each card's page): rewards, milestones, lounge,
fees, exclusions and caps, each with an optional yearly value and where it came from. A card starts from its scheme's
published terms, every entry marked *to check* until you confirm it; after that the list is yours. They are
documentation, not inputs: nothing in the reward maths reads them. **Edit details** changes a card's name, bank, digits,
network, notes, scheme, limit, fees and cycle. Every card has a fixed colour (its `slot`, by id) used on every screen.

**Which card for what** (Cards overview) shows the best card per kind of spend and what the wrong card cost over 12
months. Rates are the issuers' published terms in `card_advisor.py` (marked assumed or measured where they are not
published); point values (Rs 0.25 a point, Rs 1 a NeuCoin) are assumptions. Caps, milestones, lounges and fees are not
in the rates. A merchant correction on a card replaces the earlier one for that merchant.

Open **Cards** in the top bar. **All cards** is the usage view: total and last-12-month spend,
fees and interest, one tile per card (period of use, spend, EMI share, fees, top merchant, and
whether the card is still in use), spend by financial year split by card, and every bill's pay
date in one list. One pill per card opens that card.

**Import.** *Import statements* takes one or more PDFs, from any mix of cards. The password
is used for that one request and is never stored, and the PDF is not kept, only the parsed
rows. Each statement names its own card (issuer plus last digits) and the card is created
from it the first time, so there is no card to pick.

**Which statements can be read.** There is no general-purpose PDF parser; each bank layout
needs its own reader, registered in `PARSERS` in `spendlens/cards.py` as a detector plus a
parser. Today: **SBI Card** (monthly cycle statements, `cards.py`), **ICICI Bank** (`cards_icici.py`, yearly
account transaction lists), **Bank of Baroda / BOBCARD** (`cards_bob.py`, monthly statements in two
PDF layouts), **HDFC Bank** (`cards_hdfc.py`, Tata Neu PDF statements) and **American Express**
(`cards_amex.py`, `.xlsx` exports). Anything else is reported as unrecognised rather than guessed at.

**One file, several cards; one bill, several cards.** An ICICI list is per *account*: it has a
section for each card number and an account-level section for items like reward-redemption fees
(which go to the card in use on that date). Cards listed on one statement share a bill, so they
are put on one **billing account**. Payments are posted under one card yet settle the whole bill,
so the *when to pay* maths takes every card on the account, while spend stays per card. Editing
the billing cycle applies to every card on the bill, because they share one due date.

**Re-issued cards.** A bank re-issues a card under a new number. A number that starts within 120
days after another stops, on the same bill and without overlapping it, is treated as that
card's replacement; two numbers used at the same time are two cards. This is an *inference* from
the dates, recomputed on every read (so it does not depend on upload order), and the page lists
every number of a card so a wrong grouping is visible. Unknown ICICI cards start as *usage only*:
no reward scheme is assumed. Edit a card to name it and to pick a scheme (Amazon Pay ICICI, SBI
Cashback), which resets its rates to that scheme's published ones.

**How a file is checked.** SBI and BOB print their totals (BOB: opening balance, payments, new purchases,
closing balance), so the parsed transactions must add up to them. ICICI's yearly list prints no totals at all, so the check is
*coverage*: every date-led line must parse, or the file is rejected whole. Either way a file
is imported completely or not at all, and re-uploading is safe: every row has a hash, and two
genuinely identical lines on one day each keep their own.

**Claude fallback (optional, off by default).** For a format with no reader, set
`ANTHROPIC_API_KEY` in the backend's environment and restart; the dialog then offers *Use
Claude for formats without a built-in reader*. The statement's text is sent to Anthropic, so
it is opt-in per upload. Claude's reply is never trusted: fields are type-checked, `is_spend`
is derived locally, and the transactions must add up to the statement's own purchases total
or the whole file is rejected. A statement a built-in reader recognises never goes to Claude.
The key is read from the environment and never stored.

**When to pay.** The top panel works out the best day to pay each card's bill. A card lends
you the money free from the day you spend until the bill's due date, so paying the day the bill
arrives, or paying as you go, hands that float back. Paying *after* the due date costs a fee
plus roughly 45% a year on the whole cycle. So the pay date is the due date minus a safety
margin (default 1 day), stepped back off a weekend. It needs a **billing cycle**: a statement
day and the days to the due date. SBI prints both, so they are read and marked *verified*;
ICICI's yearly list prints neither, so its cycle is inferred and marked *assumed* until you
confirm it from a monthly statement (Edit). The panel also shows how you actually pay: the days
of free credit you use against what was available, how early you pay, and what that costs a
year at the rate your idle money earns (a setting, default 7%; it is the savings or liquid-fund
rate, not what the card charges). Payments are matched to spends oldest first, so each rupee
paid is tied to the spend it settled. The logic is in `spendlens/card_float.py`, as pure
functions of dates and amounts.

**Rewards.** The SBI statement prints the cashback it paid, so the page shows it beside what
the rules compute; the gap is the measure of how well the rules fit, and choosing a merchant's
kind corrects it (saved as a rule, re-applied to all history). The ICICI list prints no reward,
so it is *estimated* from the card's rates and labelled as such. Refunds take their reward
back. Rates are per card and editable (Edit), since 5% on Amazon needs Prime and is 3% without.

Card spend is stored in `card_txns`, deliberately **not** merged into `expenses`: statements
cover months that already have hand-entered expenses, so merging would double count. See
[CREDIT_CARDS.md](CREDIT_CARDS.md) for the model, what the real statements showed, and what is
still to build.

## Expense page shortcuts

Click a cell, then just type an amount (Enter saves, Tab saves and moves right, Esc cancels). Enter on a selected cell opens the detail editor (sub-category, note, several lines); Del clears a single-entry cell; arrow keys move the selection; **N** opens *Add expense*; **[** and **]** change the month. The add dialog remembers your last category and sub-category.

## Expense dashboard

- **Spent** – spend against the budget cap, with a marker for where you should be today and an on-pace / ahead / under chip. Cashback is shown in the sub-line.
- **Left to spend** – cap minus spend, with an amount per remaining day (current month). Past months show *Left unspent* / *Overspent*.
- **Projected month-end** – current month only, from the forecast model with a likely range. Past months show **vs other months**: the two previous months and the following month.
- **Savings rate** – actual saving rate against the planned one.
- **Where it went** – ranked categories, over-target first, with a target tick and ₹ over/under; click a row for its sub-categories.
- **Pace** – cumulative spend vs the budget line, last month as a faint line, forecast as a dotted line with a range.
- **12 months** – spend bars with the budget cap per month; click a bar to open that month.
- **Worth a look** and **Largest expenses** – automatic notes and the month's top five entries.
- **Forecast card** (current month) – next month's total, range and top categories, with the backtest error.

## Forecasting (`spendlens/forecast.py`, `GET /forecast?month=`)

Baseline model, no ML library. Per category: median of the last 6 months with data, nudged 30% towards the same month last year; steady items (e.g. rent) use their latest amount. The range is the 10th–90th percentile of those months. For the current month, spend so far is blended with the run rate. A 12-month backtest (each month predicted from earlier data only) is compared with "same as last month"; the dashboard shows both errors and marks categories as *low confidence* when the model does not beat that baseline. It needs at least 3 months of earlier data. Roadmap (lumpy annual payments, real ML models, stored forecasts): `plan/spendlens-forecasting-ml-plan.md`.

## Admin tools

Open **Admin** in the top bar; tools are listed in a left-hand menu. New tools are added in the `ADMIN_TOOLS` list in `artifacts/spendlens/src/components/Admin.tsx`.

**Categories** – add, edit, reorder, archive, restore, delete. History is never rewritten:
- A new category starts in the chosen month (default: current); earlier months never show it.
- *Archive* hides a category from a chosen month onward (default: **next month**, so the current month stays complete). It stays, with all amounts, in every earlier month and can be restored.
- A month that already contains entries for a category always shows it, so totals can't disagree with the data.
- *Delete* is only offered for categories that never had an expense.
- Name / icon / colour are labels and change in every month; no amounts change.

**Sub-categories** – each category can be split (e.g. Transport → Fuel, Cab & Auto, Parking). Pick one per entry in the cell editor (select a day and press Enter, or double-click it; add several lines per day) or in *Add expense*. Expand a category row (▶) to see its sub-categories per day. Sub-categories follow the same rules as categories (start month, archive from a month, restore, delete only if unused), are for reporting only (targets stay at category level), and feed the dashboard's "Where it went" detail. Existing entries were mapped automatically from their notes; the *Needs review* tab lists the rest, and mapping a note applies to every entry with that note and is remembered. Unmapped entries show as "Unassigned", so category totals never change.

**Targets & Budget** – you enter *total salary* and *total saving* (₹); the *budget cap* is salary − saving and is editable too (editing it changes saving). Category targets are % of salary, accept decimals, and can be edited as % or ₹/month (the other updates). Their sum is the *expense target*; expense target + saving must equal 100% of salary and Save is blocked above that. Saving stays fixed: a *Balancing category* (default Miscellaneous, changeable or off) absorbs any change you make to another target, the salary or the saving, so the total stays at 100%. Everything is *effective-dated*: a change applies from the month you pick, and earlier months keep the values they had. Salary can differ per month (add a row from that month); the change history is shown on the same page.

When an older database is upgraded, the app first copies it next to the original (`spendlens_v2.pre-admin.bak`, `spendlens_v2.pre-subcat.bak`). These are created only once, during that migration, and can be deleted afterwards.

## Notes

- The Holdings page groups rows by `grp`, managed in Admin → Holding groups (add, rename, delete; deleting moves holdings to the built-in Others bucket, empty `grp`), shows monthly SIPs and flags FDs that mature within 90 days. Click a row to edit; Delete is inside the edit dialog.
- **Fixed-rate holdings.** Tick *Manual value* to switch auto-calculation off and keep the present value you type. *Credited yearly* mode is for cumulative FDs: value = principal + the interest credits you enter (date, amount per line) with later yearly credits projected at the rate; no interest is shown between credit dates. Give a holding an interest rate, opening date and (optionally) closing date and its present value is computed on every read: invested amount grown at the rate (quarterly, annual or simple), each SIP growing from its own date, frozen at the closing date. Nothing is stored, so changing the rate or dates takes effect at once. Tick *Recurring deposit* for an RD: it then uses one deposit of the SIP amount per month from the opening date (each earning interest from its own date) and invested becomes the sum of those deposits.
- **Edit holding: auto-calculation and auto deposit.** There is no setting literally called "auto deposit"; the *Recurring deposit* checkbox does it (Invested then shows *Auto (deposits)*). What the form does depends on interest rate + opening date, *Manual value*, *Recurring deposit* and *Monthly SIP* (`Holdings.tsx`, `spendlens/accrual.py`):

  | Rate + opening date | Manual value | Recurring deposit | Monthly SIP | Invested | Present value | Behaviour |
  |---|---|---|---|---|---|---|
  | Missing (either) | any | any | any | typed | typed | No auto-calculation; the form hints to add a rate and opening date. |
  | Both set | ticked | any | any | typed | typed | Auto-calculation off; typed values kept. |
  | Both set | off | off | 0 | typed | **auto** | Invested grows at the rate from the opening date. |
  | Both set | off | off | > 0 | typed | **auto** | Opening principal grows from the opening date; each SIP the app applies on the SIP day grows from its own date. |
  | Both set | off | on | 0 | typed | **auto** | Same as the row above with SIP 0: Recurring deposit does nothing without a SIP amount. |
  | Both set | off | **on** | **> 0** | **Auto (deposits)** | **auto** | **Auto-deposit mode.** One deposit of the SIP amount on the opening date, then one on the SIP day of each following month; each earns interest from its own date. Invested = SIP × number of deposits. |

  Other fields: the *closing date* stops deposits and growth and freezes the present value there. *Compounding* is Quarterly, Annual, Simple or Credited yearly; *Credited yearly* (cumulative FD) and its credits box apply only when Recurring deposit is off (with it on, the value compounds quarterly). *SIP day* blank uses the opening date's day; short months use their last day. Use Recurring deposit for a bank RD or any fixed monthly deposit; leave it off for an FD or PF where you enter the invested amount.
- **Exposure and tags.** Every holding has a *group* (where it sits, e.g. Mutual Funds), one *exposure* (Equity / Gold / Debt / Cash: what it is really invested in) and optional *tags* (sector or theme). Exposure is filled in automatically: EQ → Equity; GOLD or any fund with "gold" in the name → Gold; FD and PF → Debt; CASH → Cash; funds from their name (cap / ELSS / flexi → Equity, arbitrage and debt funds → Debt, liquid → Cash). For the mix calculations Cash counts as Debt, so there are three exposures. The holding dialog has an Exposure box (Auto keeps the current value) and a Tags box. Tags start from the old Sector label (stocks, funds) and *Emergency* for the emergency fund; classification now lives in tags, the *Sector* column is kept only as *Institution / purpose* (bank or goal, mainly for FDs and PFs) and the Portfolio dashboard's "Equity by sector" uses each stock's first tag. The **Dashboard → Asset Mix** tab shows allocation by exposure (donut and table with gain and drift from target), exposure by group, and a themes / sectors breakdown (`GET /portfolio/exposure`).
- **SIP mix plan (Asset Mix tab).** Set a target Equity / Gold / Debt ratio, expected yearly returns, a "reach within N years" window and a forecast length in Admin → Goals & targets (`PUT /portfolio/mix-plan`, stored in `portfolio_plan` as `mix_targets`, `mix_returns`, `mix_reach_years`, `mix_years`). `GET /portfolio/mix` returns today's SIP split by exposure, a forecast, and the SIP split that reaches the target. Only where new SIPs go changes; nothing is sold. For each month N it solves for the constant SIP shares that put the mix on target at month N (an exposure already above target would need a negative SIP and is held at 0); the first N that works is the earliest possible date, and the split for your chosen window (a gentler change) is the one suggested, switching to the target ratio afterwards. The forecast is one deterministic path at the expected returns, with SIPs stepping up by the yearly rise set in the same admin page.
- **SIPs.** Set an amount and day per holding (Admin → Holding groups → expand a group, or the holding dialog). On that day the amount is added to the holding's invested and present value (units added at the current price for stocks and gold). It runs when the data is read, so missed months are caught up; each application is logged (`sip_log`) and never applied twice. Manual edits are never recalculated.
- **Portfolio dashboard.** KPIs come from `GET /portfolio/kpis` (`spendlens/portfolio.py`): net worth, gain, XIRR, yearly investing, emergency cover (months of average spend), allocation versus target by group with the amount to add or trim, concentration, sector split, fixed-income yield, best and worst holdings. A value snapshot is stored daily in `portfolio_snapshots` when the app is opened; the 30-day change, history curve and XIRR build from those (XIRR needs 60 days). Goals (`portfolio_goals`), target allocation and return assumptions (`portfolio_plan`) are edited in Admin → Goals & targets. The goal projection is a Monte Carlo simulation, not a trained model: each group grows at its own return and volatility, current SIPs continue and step up yearly, goals are paid out in their year, and the P10/P50/P90 range and per-goal funding odds come from 1,500 paths (plus a lower-returns case). The emergency fund is excluded from goal money.
- **Daily prices** (`spendlens/prices.py`, Admin → Prices). Holdings with *Auto* ticked are updated by a background thread that checks every 15 minutes and runs after 19:00 and 22:30 on weekdays, and straight after start-up if a run was missed (so the app only needs to be open at some point). Equity: NSE symbol in `holdings.ticker`, last close and 52-week high/low from Yahoo Finance's chart endpoint (unofficial, no key). Mutual funds: AMFI scheme code and `units`, value = units × NAV from AMFI's `NAVAll.txt`; MFs stay one line (qty 1, cmp = value) and SIPs buy units at that day's NAV. *Auto-map* suggests symbols (kept only if the live price is within 35% of the stored one) and Direct-Growth scheme codes; *= value → units* fixes the units from today's value. A failed source leaves the old value and shows the reason; every run is logged in `price_runs`, daily prices in `price_history`, and a portfolio snapshot is saved after each run. Gold and fixed-return holdings are not fetched.
- **Ledger** (`spendlens/equity.py`, `equity_import.py`, `dividend_agent.py`; Ledger page). Broker files are imported from a folder, not through the UI: put Zerodha Console files in one sub-folder per demat account (`tradebook/SK`, `tradebook/SS`; the folder name is the account label) — equity tradebooks (one per financial year), dividend statements (keep the file name, it carries the period) and the holdings statement — stop the backend, and run `python spendlens\import_broker.py tradebook` (`--events actions.json` also adds corporate actions; `--email` picks the user). Re-running is safe (stored trades are skipped, a statement replaces its period), so new files can be added and the command run again. Everything is stored in the database, so the files can be deleted. Trades are replayed with corporate actions into FIFO lots: splits come from Yahoo on Refresh, a few Yahoo misses are built in (Bajaj Finance's 2025 bonus, the Aarti Pharmalabs demerger), and account-specific ones (IPO allotments, buyback tenders, transfers) are added on the Corporate actions tab, usually from an Audit issue's *Fix…* button. The Audit tab checks the share count on every dividend-statement ex-date and on the holdings statement; shares with no known cost are left out of XIRR. Dividend statements are the record of what was paid; after their last day Refresh fills dividends from Yahoo (whose amounts are split-adjusted, so they are multiplied back) for the shares held the day before each ex-date, from 2023. XIRR uses buys out, sales / buybacks / dividends in and today's value; brokerage isn't in the tradebook. The `transactions` table stays for SIP flows, which the Holdings XIRR KPI uses; the old manual-entry Ledger screen is gone.
- Holdings of type MF / FD / PF are entered as invested + present value (stored as quantity 1 × amounts); EQ / GOLD / CASH use quantity × price.
- Data lives only in `spendlens/spendlens_v2.db`; copy that file to back it up.

**Reward schemes.** A card's *scheme* (Edit) decides how rewards are worked out. *Amazon Pay ICICI*, *ICICI
Rubyx* and *ICICI Sapphiro* estimate points from the bank's published rates (Rubyx and Sapphiro: 4 points per
Rs 100 international, 2 domestic, 1 on utilities and insurance, none on fuel; a point valued at Rs 0.25, which the
bank's page does not state, so it is an assumption). Rubyx and Sapphiro also get a **benefits panel**: the yearly
milestone (Rubyx 3,000 points at Rs 3L and 1,500 per further lakh to 15,000; Sapphiro 4,000 at Rs 4L and 2,000 per
lakh to 20,000), lounge quarters, and what redeeming costs (Rs 99 plus GST each). *BOB Eterna* needs no estimate:
its statements print the points per transaction and in total, so rewards are read, and only the rupee value of a
point (Rs 0.25) is assumed. A product is never guessed from a folder name or a number series: the ICICI statements
do not name it, so you set it.

**Missing statements.** If a monthly statement is missing from a run (say August between July and September),
the cycle that would have shown that month's payments is unseen. Pay timing is therefore worked out within each
unbroken run of statements, never across the gap, so a missing month cannot appear as a late payment; the page
names the missing statement.
