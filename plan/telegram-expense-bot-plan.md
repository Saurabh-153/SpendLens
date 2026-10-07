# Plan: Telegram expense bot for SpendLens (works while PC is off)

## Context
Add expenses to the SpendLens expense dashboard from a phone chat, with no LLM. SpendLens runs only on the user's local Windows PC (FastAPI + SQLite, `spendlens/app.py`). The PC is often off, so messages must queue on the chat provider's side and be polled and applied when SpendLens next starts.

Telegram fits this: bots use long polling (`getUpdates`), so no public URL or tunnel is needed. Telegram stores undelivered updates for **24 hours** and hands them over when the bot next polls. WhatsApp can't do this without a public always-on webhook.

## Offline-aware design
- Messages must be self-contained, because the bot can't ask follow-up questions while the PC is off.
  - **Quick format (works offline):** `450 groceries milk and eggs` or `450 food #yesterday`. A regex parses amount, category keyword and note.
  - **Guided flow (online only):** `/add` shows category buttons (inline keyboard) from `categories_for_month` (`spendlens/database.py:39`).
- **Date comes from the Telegram message timestamp** (`message.date`, converted to local time), never from processing time. An expense sent Tuesday and processed Thursday is recorded on Tuesday. `#yesterday` and `#dd/mm` override it.
- **On startup:** poll from the stored offset, process the backlog oldest-first, and send one summary reply: "Caught up: 3 added, 1 couldn't parse (reply with a fix)".
- **Unparseable or ambiguous messages** get a reply on catch-up and nothing is inserted. A parseable message with no category match goes to Miscellaneous (id 19) and says so.

## Implementation
1. **`spendlens/telegram_bot.py` (new).** Long-polling loop in a daemon thread, started from `spendlens/app.py` next to the price scheduler (line 27).
   - Use `httpx` or `requests` directly against the Bot API. This avoids a heavy dependency, so add one line to `spendlens/requirements.txt`.
   - Persist the poll offset (`last_update_id`) in a new tiny table `bot_state`.
   - Parser module: pure functions, easy to test.
   - Category keyword map: category names plus sub-category rules via `load_rules` and `match_rules` (`spendlens/subcategories.py:136,141`).
2. **Insert path:** call `create_expense(ExpenseCreate(...))` (`spendlens/routes/api.py:737`, model at 68) so `ensure_category_open` and `ensure_sub_ok` validation is reused. Closed categories produce a friendly error reply.
3. **Dedupe migration:** add migration 12 to `MIGRATIONS` (`spendlens/database.py:343`) with `expenses.source_msg_id TEXT` plus a unique index (`telegram:<update_id>`). Restarts and retries then cannot double insert. The existing `cards._row_hash` with `INSERT OR IGNORE` is the pattern to copy. `create_expense` needs an optional `source_msg_id` argument.
4. **Security (the API itself has no auth):** an env var `TELEGRAM_ALLOWED_USER_IDS` allow-list and `TELEGRAM_BOT_TOKEN`. Messages from other users are silently dropped. The token is read from the environment only and never committed.
5. **Commands:** `/add` (guided), `/today`, `/month` (reads the same data as `GET /dashboard`, `api.py:776`), `/undo` (deletes the last bot-created row, via `source_msg_id`), `/help`.
6. **Optional phase 2, only if 24h isn't enough:** a free Cloudflare Worker + KV as an always-on relay that receives Telegram webhooks, stores messages with no expiry, and instantly replies "Saved, will sync". SpendLens then polls the Worker instead of Telegram. Skipped unless the user asks.

## Critical files
- `spendlens/telegram_bot.py` (new), `spendlens/app.py`, `spendlens/database.py` (migration 12), `spendlens/routes/api.py` (`create_expense` optional `source_msg_id`), `spendlens/requirements.txt`
- `tests/test_telegram_parser.py` (new), `tests/test_telegram_bot.py` (new), `DATA_MODEL.md` (document the new column)

## Telegram setup (walk through together, first step after approval)
1. Install Telegram on the phone and sign in.
2. Search for **@BotFather** (blue verified tick) and send `/newbot`.
3. Give it a display name (e.g. "SpendLens") and a username ending in `bot` (e.g. `saurabh_spendlens_bot`).
4. Copy the token BotFather sends. Treat it like a password: never paste it in chat or commit it.
5. Open the new bot, press Start, and send any message. `/whoami` (built in step 1 of implementation) replies with the numeric user ID.
6. In PowerShell, set the env vars before starting the app:
   `$env:TELEGRAM_BOT_TOKEN="<token>"; $env:TELEGRAM_ALLOWED_USER_IDS="<your id>"; python spendlens\app.py`
   For a permanent setup, use `setx` or a git-ignored `.env`.
7. Optional: in BotFather, `/setcommands` to list `add`, `today`, `month`, `undo`, `help` in the phone's command menu.

## Housekeeping
- On approval, save this plan to `ExpenseTrack\docs\telegram-expense-bot-plan.md`.

## Verification
- `python -m pytest`: parser tests (amounts like `450`, `1,250.50`, `₹450`; categories; `#yesterday`; garbage input), plus a bot test with a fake Telegram HTTP client feeding a batch of queued updates. It must show correct dates from message timestamps, no duplicates when the same batch is replayed, allow-list enforcement, and the offset persisted.
- Migration test, following `tests/test_migrations.py`.
- Manual end-to-end:
  1. Stop SpendLens.
  2. Send `450 groceries test` from the phone.
  3. Start SpendLens.
  4. Confirm the catch-up reply on the phone and the row on the dashboard under the right date and category.
  5. Restart and confirm no duplicate.
- `pnpm run check` for typecheck, build and tests.

## Known limits
- Backlog older than 24 hours is lost (Telegram's limit). Phase 2 relay removes this.
- No confirmation reply while the PC is off. The phone shows a sent message only. Phase 2 relay adds an instant acknowledgement.
- `user_id` is hard-coded to 1 today, so shared or group expenses are all recorded as one user unless the user wants a payer field (out of scope here).
