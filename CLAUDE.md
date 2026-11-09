# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

SpendLens: a personal expense, portfolio and credit-card tracker (₹, lakh/crore formatting). FastAPI + SQLAlchemy
backend in `spendlens/`, React 19 + Vite + TypeScript frontend in `artifacts/spendlens/` (a pnpm workspace package).
Windows/PowerShell is the primary dev environment; the Python venv is `venv_expense\`.

## Commands

Run from the repo root.

```powershell
# setup
python -m venv venv_expense; .\venv_expense\Scripts\activate
pip install -r spendlens\requirements-dev.txt
pnpm install

# run: single server (API + built UI on :5000)
pnpm build; python spendlens\app.py      # or .\run-api.ps1 (loads DATABASE_URL from .env.local)
# run: dev with hot reload (Vite on :3000 proxies /spendlens/api -> :5000)
python spendlens\app.py                  # terminal 1
pnpm dev                                 # terminal 2

# checks (CI runs all of these)
python -m pytest                         # or: pnpm run test
python -m pytest tests/test_isolation.py::test_new_user_starts_with_defaults_and_no_data   # one test
pnpm run typecheck
pnpm run build
pnpm run check                           # typecheck + build + tests

# tests on PostgreSQL (database name must end in _test; it is wiped every run)
$env:TEST_DATABASE_URL = "postgresql+psycopg://user:pass@localhost:5433/spendlens_test"; python -m pytest
# or put TEST_DATABASE_URL in .env.local and set $env:SPENDLENS_TEST_PG = "1"

# migrations
.\venv_expense\Scripts\python -m alembic revision -m "describe the change"
.\venv_expense\Scripts\python -m alembic upgrade head
```

The backend doesn't hot-reload: restart `app.py` after a Python change. A stale backend still holding port 5000
causes "Address already in use" errors and odd behaviour. Swagger is at `http://localhost:5000/docs` (on while the
backend binds 127.0.0.1, its default; `SPENDLENS_DOCS=1` keeps it on a network bind). `security.py` adds the
cross-site Origin check, CSP and headers (`install(app, ...)`) and the sign-in / reset-code throttles.

## Architecture

**Backend imports are flat.** `spendlens/` is on `sys.path` (app.py runs from there, and conftest inserts it), so
modules import each other as `import auth`, `from db.engine import SessionLocal`, `from db.scope import user_of`,
not as `spendlens.x`.

**Request path.** Everything is under `/spendlens/api`. `routes/api.py` combines the domain routers (expense,
investing, card, reminder, tracker, status, auth) under one `APIRouter` whose dependency is `auth.guard`. The
guard checks the `sl_session` cookie, maps the URL's first path segment to a module through
`auth.MODULE_OF_PATH` (expense / holdings / ledger / cards), checks the user's `ModuleGrant`s
(`ADMIN_ONLY` = `database`, `admin`), and sets `session.info["user_id"]`. **A new route prefix must be added to
`MODULE_OF_PATH`.** Otherwise it only needs a signed-in user. The frontend's locked tabs (`LockedModule.tsx`) are
cosmetic; the backend is the authority.

**Multi-user scoping is automatic for ORM queries.** `db/scope.py` hooks `do_orm_execute` so that any
SELECT/UPDATE/DELETE on a model with a `user_id` column is filtered to the session's user, and new rows are stamped
with it. Raw `text()` SQL is **not** covered: `cards.py` passes `:uid` and writes its own `user_id` conditions.
Sessions without `info["user_id"]` (scheduler, start-up, direct DB tests) are unscoped, and `user_of(session)`
falls back to user 1, the bootstrap admin who owns pre-multiuser data (`auth.bootstrap_admin`, configured with
`SPENDLENS_ADMIN_EMAIL`/`SPENDLENS_ADMIN_PASSWORD`). `tests/test_isolation.py` checks that users can't see each
other's data, so extend it when adding user-owned tables.

**Two databases, one main.** `db/engine.py` uses PostgreSQL when `DATABASE_URL` is set (app.py reads it from the
git-ignored `.env.local`), otherwise the SQLite file `spendlens/spendlens_v2.db` (`SPENDLENS_DB` overrides).
With PostgreSQL, `db/failover.py` decides which database is main (persisted in `spendlens/database-mode.json`),
handles the switch, and falls back to the SQLite mirror **read-only** when PostgreSQL is unreachable. Its
middleware returns 503 on writes during a switch or the fallback. `db/mirror.py` + `db/replicate.py` keep the
other database a table-by-table verified copy. Without `DATABASE_URL` none of this runs.

**Alembic owns the schema.** On start-up `db/migrate.py:prepare_database()` runs `alembic upgrade head`. Baseline
`218d401380ff` creates the pre-Alembic tables and starter data (`db/seed.py`). The legacy `database.init_db()` /
`MIGRATIONS` path (the only remaining `sqlite3` use) exists only to adopt old SQLite files with no
`alembic_version`. Migrations must run on **both** SQLite and PostgreSQL: use `db/ddl.py` helpers (`now_text`
for timestamp defaults, `sync_sequences` after explicit-id inserts), `sa.true()`/`sa.false()` for boolean
defaults, and guard against work an earlier revision may already have done (see `459d2bc3ff86`,
`7fa60c624af4`). Models live in `spendlens/db/models/`. Review autogenerate output by hand. Test upgrade →
downgrade → upgrade on a scratch copy of the SQLite file and on the PG test database, never on the real file.

**Domain modules** are plain Python called by the routers: `portfolio.py` (KPIs, snapshots, XIRR, goal Monte
Carlo), `ledger.py`, `sip.py`/`accrual.py` (applied lazily on read, logged in `sip_log` so it's never applied
twice; FD/RD values computed, not stored), `prices.py` (background scheduler for Yahoo/AMFI prices),
`forecast.py`, `subcategories.py`, `cards.py` (with per-bank parsers `cards_<bank>.py` registered in `PARSERS`,
and an opt-in Anthropic fallback in `_llm_complete` that tests replace), `card_float.py`, `card_advisor.py`,
`card_perks.py`. Card dates, SIP dates, holidays and tracker KPIs on the calendar are computed, not stored. Table
relationships are documented in `DATA_MODEL.md`.

**Frontend.** `src/api.ts` is the single typed client used by every page. `App.tsx` handles top-bar navigation
and URL params (`?page=…&tab=…&tool=…`), and `auth.tsx` + `Login.tsx` handle sign-in. Admin tools are registered
in `ADMIN_TOOLS` in `components/Admin.tsx`, with the tools themselves in `components/admin/`. Shared primitives
(Card, Modal, Field, …) are in `components/ui.tsx`. There is no frontend test suite, so typecheck + build is the
gate.

## Tests

- `tests/conftest.py` sets `SPENDLENS_DB` to a temp file **before** any backend import and builds it with
  Alembic (same path as app.py), plus `FIXTURE_HOLDINGS`. The suite never touches `spendlens_v2.db`. Tests that
  want real data use the `real_db_copy` fixture and skip when the file is absent or on PostgreSQL
  (`sqlite_only` marker).
- Fixtures: `client` (signed-in admin), `make_user(modules=..., role=...)` for extra users, `anon_client`,
  `blank_db`, `real_db_copy`, `unmigrated_db`.
- `tests/test_api_shape.py` pins the keys the UI reads from each read endpoint. When a response key changes,
  update `src/api.ts` and this test together.
- CI (`.github/workflows/ci.yml`) runs ruff, pytest on SQLite, then on PostgreSQL 16, then `pnpm install
  --frozen-lockfile`, typecheck and build. `.npmrc` must stay consistent with `pnpm-lock.yaml`. CI is the gate.
  The Claude workflows below only comment or propose.
- `claude.yml`: `@claude` in an issue or PR (owner and collaborators only; the repo is public) runs Claude with the
  same toolchain, SQLite tests only. `claude-review.yml`: an automatic read-only review of PRs touching code,
  following `.claude/agents/isolation-reviewer.md` and `migration-author.md`. Both need the `ANTHROPIC_API_KEY` or
  `CLAUDE_CODE_OAUTH_TOKEN` secret (`/install-github-app`).

## Claude Code hooks (`.claude/`)

- `guard.py` (before shell commands) refuses `alembic upgrade/downgrade/stamp` unless the same command sets
  `SPENDLENS_DB` to a scratch file or `DATABASE_URL` to a `*_test` database. It also refuses deleting or
  overwriting the database, mirror and mode files and reading or writing `.env.local`, refuses force pushes, and asks
  before `reset --hard`, `clean`, `checkout --`, `restore`, `stash drop` and `branch -D`.
- `after_edit.py` runs `ruff check --fix` (config in `ruff.toml`) on each edited `.py` file and reports what's left.
- `stop_check.py` runs `pnpm run typecheck` (if TS changed) and the tests mapped to the edited Python files before a
  turn may end. It blocks up to 3 times. The full suite and `pnpm run check` are still yours to run before committing.

## Subagents (`.claude/agents/`)

`migration-author` (model + Alembic revision, proven on scratch SQLite and on PG), `route-builder` (route +
`MODULE_OF_PATH` + scoping + `api.ts` + shape/isolation tests), `card-parser` (`cards_<bank>.py` that reconciles to
printed totals, registered in `PARSERS`), `isolation-reviewer` (read-only, multi-user leak review of a diff), and
`pg-tester` (CI's checks on SQLite and PostgreSQL, diagnoses failures), and `mf-factsheet-analyst` (reads factsheets/YYYY-MM/ into validated JSON for MF Analysis; never touches the database). A schema change lands before the routes
that use it. Run `isolation-reviewer` on anything touching routes, models, migrations or `cards.py`.

## Skills (`.claude/skills/`)

`/mf-factsheets` (extract factsheets with mf-factsheet-analyst, verify, then `import_mf.py`). `/new-migration`, `/new-route` and `/new-card-parser` pin down the contract and hand off to the matching subagent,
then verify its report. `/check-all [quick]` runs CI's checks plus ruff through `pg-tester`. `/feature <desc>`
(user-invoked only) does plan → approval → branch → subagents → isolation review → `/code-review` → `/check-all` →
a local commit of only the feature's files. `/parallel <task>; <task>` (user-invoked only) runs independent tasks
in worktree subagents and merges them back one at a time.

## Worktrees

- New worktrees branch from local `HEAD` (`worktree.baseRef: head`), not `origin/main`, which is far behind. They see
  only **committed** work.
- A worktree has no `venv_expense/` (use the main checkout's python; the hooks do), no `node_modules/`
  (`worktree_setup.py` installs it from the pnpm store at session start), and deliberately no `.env.local`.
- **Never run PostgreSQL tests in a worktree.** Every run drops and rebuilds the single shared `_test` database, so
  parallel runs destroy each other. PostgreSQL runs once in the main checkout after merging.
- Remove a worktree with `python .claude/scripts/worktree_remove.py <path>`. Plain `git worktree remove` fails on
  pnpm's `node_modules` on Windows.

## Docs in the repo

`README.md` (user-facing behaviour, run modes, troubleshooting), `DATA_MODEL.md`, `CREDIT_CARDS.md`,
`ROADMAP.md`, and `plan/` (forecasting/ML, scale, monetization, Telegram bot plans). Parts of the README
predate the multi-user auth on the current branch.
