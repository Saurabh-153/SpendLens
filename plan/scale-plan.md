# SpendLens scale plan: from one owner to 1,000+ users

Checked against the code on 2026-10-18, after per-user login, module access and data isolation were added
(branch `feature/sqlalchemy-alembic-multiuser`).

**Status: only step 2 (indexes) is done. Everything else is deliberately deferred; build it when the launch date or the load test asks for it.**

Not load-tested yet: every number below comes from reading the code
or a quick measurement, and step 7 is where real numbers replace them.

Related: [monetization-plan.md](monetization-plan.md) M0 already lists "move to Postgres" and "run the price scheduler as a
separate worker". This plan is the detail for those two lines and for what comes with them.

## What "1,000 users" means

| Case | Rough load | Where it stands today |
|---|---|---|
| 1,000 registered, each opens the app a few times a day | a few requests per second | Needs steps 1–3 |
| 1,000 active in the same hour | tens of requests per second | Needs steps 1–5 |
| 1,000 at the same moment | hundreds of requests per second | Needs steps 1–7 and real testing |

## Findings (each one checked)

| # | Finding | Evidence | Status |
|---|---|---|---|
| 1 | The SQLite mirror is a full copy of the database. It rebuilds every table into a temp file, verifies it, then swaps it in, ~10 s after the last save (each save pushes it back) and at least every 15 minutes. The cost grows with total data, not with traffic. | `db/mirror.py` (`debounce=10`, `period=900`, `replicate.copy_all`) | Open |
| 2 | One server process. `uvicorn.run(app, ...)` with no workers. The mirror, failover state and price scheduler live in that process, so several workers would each run their own. | `app.py:67`, `db/failover.py` (`_instance`), `prices.start_scheduler` | Open |
| 3 | Connection pool is SQLAlchemy's default (5 + 10 overflow). Every request opens a session and the sign-in check adds up to 3 queries (session, user, grants). | `db/engine.py` (`create_engine` with no pool settings), `auth.guard` | Open |
| 4 | Logging in costs ~170 ms of CPU for bcrypt (measured), on a request thread. Sync routes run on a pool of ~40 threads. | `auth.check_password`, FastAPI threadpool | Open |
| 5 | No index on `user_id` anywhere, and none on `expenses.date`. Only `card_perks`, `card_txns` (card, date), one on reminders and one on snapshots existed. Every query now filters by `user_id`. | `grep create_index` over `alembic/versions` | **Done** (step 2) |
| 6 | Heavy work happens inside requests: statement PDF parsing (`cards.import_files`) and the dashboards. | `routes/card_routes.py` upload, `routes/expense_routes.py` dashboard | Open |
| 7 | The daily job is serial: price fetch for every user's holdings, SIP application, then one snapshot per user. Yahoo requests are rate-limited. | `routes/investing_routes.py` `refresh_and_snapshot`, `prices.run_refresh` | Open |
| 8 | Expired login sessions are never deleted, so `auth_sessions` only grows. | `auth.py` (no cleanup) | Open |
| 9 | No limit on login attempts. | `routes/auth_routes.py` `login` | Open |

Not a problem: data isolation costs one extra `WHERE user_id = ?` per query (see `db/scope.py`), and prices are fetched once per
holding, not per user.

## Steps, in order

### 1. Hosted mode without the mirror (finding 1): deferred
- Add `SPENDLENS_HOSTED=1`. In that mode `failover.startup()` skips the mirror, the read-only fallback and the PostgreSQL sync,
  and the database health check just reports status.
- Backups become PostgreSQL's own (nightly `pg_dump` or the host's snapshots), documented in the README.
- Keep the mirror for the single-owner desktop setup (default, unchanged).
- Done when: with `SPENDLENS_HOSTED=1` no copy runs after saves, `/status` says so, and the failover tests still pass.

### 2. Indexes (finding 5): DONE
Revision `b1e3a6c8d0f2` (`alembic/versions/b1e3a6c8d0f2_add_user_and_date_indexes.py`) adds 14 indexes, on SQLite and PostgreSQL:
`expenses (user_id, date)` and `(category_id)`, `categories (user_id)`, `subcategories (user_id, category_id)`,
`subcategory_rules (user_id, category_id)`, `holdings (user_id)`, `transactions (user_id, tx_date)`, `cards (user_id)`,
`card_accounts (user_id)`, `reminders (user_id)`, `trackers (user_id)`, `auth_sessions (user_id)` and `(expires_at)`,
`access_requests (status, user_id)`. `portfolio_snapshots` and `portfolio_plan` already had `(user_id, ...)` unique indexes.
Checked: the full suite passes on SQLite and PostgreSQL, and `EXPLAIN QUERY PLAN` shows the month expenses, holdings and
ledger queries using the new indexes. **Not yet checked:** the same plans at 1,000 users × 2 years of data; do that in step 7.

### 3. Connection pool and workers (findings 2, 3): deferred
- Configure the pool from environment variables (`SPENDLENS_POOL_SIZE`, `SPENDLENS_MAX_OVERFLOW`), defaults 10 + 20.
- Run `uvicorn` with several workers (or gunicorn with uvicorn workers) behind a reverse proxy; one worker per core.
- Move `start_scheduler` out of the web process into `python -m spendlens.worker`, run exactly once.
- Keep a PostgreSQL connection budget: workers × (pool + overflow) must stay under `max_connections` (or use PgBouncer).
- Done when: 4 workers run, only one process runs the scheduler, and the pool never exhausts under the load test.

### 4. Logins and housekeeping (findings 4, 8, 9): deferred
- Rate limit `/auth/login` per email and per address (for example 5 failures in 15 minutes), with a clear message. A first
  version was tried in memory (counts are per worker, so a proxy-level limit is still needed with several workers) and left out for now.
- Hourly job (in the worker) deleting expired `auth_sessions`.
- Cache the signed-in user's module list on the session row for a short time to cut the per-request queries from 3 to 1.
- Done when: a burst of wrong passwords is blocked, and `auth_sessions` stays bounded.

### 5. Move heavy work off the request path (finding 6): deferred
- Statement upload: accept the file, return a job id, parse in the worker, poll for the result.
- Dashboards: cache per user for a short time, cleared when that user saves.
- Done when: no request that parses a PDF holds a web thread for more than a second.

### 6. Parallel, polite price refresh (finding 7): deferred
- Fetch each distinct ticker/scheme once (already true) in batches with a small delay, back off on rate-limit errors.
- Snapshots per user in the worker, in chunks, so one slow user cannot stall the rest.
- Done when: the daily run for 1,000 users × 30 holdings completes inside the market-close window.

### 7. Load test (decides everything above): deferred
- Locust script: sign in, open the month grid, add an expense, open the dashboard, open Holdings; 90% reads.
- Targets to agree before running: p95 < 500 ms for reads, error rate < 0.5% at the chosen concurrent users.
- Run against a hosted-mode copy with 1,000 seeded users, and record the results here.

## Decisions I need from you
1. Hosting target (one VM, or containers) and whether you will run PostgreSQL yourself or use a managed one. It decides step 3
   (PgBouncer, number of workers) and step 1 (who does the backups).
2. The traffic you plan for in the first six months (use the table at the top). I would build 1–4 for the first launch and
   leave 5–6 until the numbers ask for them.
3. Keep the owner's mirror/fallback setup as the default for local use, and only switch it off with `SPENDLENS_HOSTED=1`.
