Plan: agent-based coding for SpendLens

Phase 1: Foundation (safety and permissions)

1. CLAUDE.md is done. Keep it updated as the architecture changes.
2. .claude/settings.json permissions:
   - Allow the safe commands agents run all the time: python -m pytest, pnpm run typecheck/build/check, alembic revision, git status/diff/log.
   - Deny reading or writing spendlens/*.db*, .env.local and spendlens/database-mode.json. These hold your real data, secrets and which database is main.
3. Safety hooks (PreToolUse):
   - Block alembic upgrade unless SPENDLENS_DB or a _test URL is set, so a migration can never hit the real file.
   - Block git push --force and anything that deletes the .bak or mirror files.

Phase 2: Fast feedback hooks

4. Add ruff to requirements-dev.txt with a small ruff.toml. A .ruff_cache exists, but there is no config and ruff isn't in the dev requirements.
5. PostToolUse hook: after any .py edit, run ruff check --fix on that file. After a .ts/.tsx edit, record that a typecheck is due.
6. Stop hook: before an agent says it's done, run pnpm run typecheck and the tests closest to the change. If they fail, the agent keeps working. This stops "done" claims on broken code.

Phase 3: Specialist subagents (.claude/agents/)

Each one is built around a rule that is easy to get wrong in this repo:

7. migration-author: writes Alembic revisions that run on both SQLite and PostgreSQL (db/ddl.py helpers, sa.true(), guard clauses), then tests upgrade → downgrade → upgrade on a scratch database.
8. route-builder: adds an endpoint end to end: router, the MODULE_OF_PATH entry, the api.ts type and test_api_shape.py keys, all together.
9. card-parser: adds a cards_<bank>.py parser, registers it in PARSERS, and writes tests in the style of test_cards_<bank>.py.
10. isolation-reviewer (read-only): checks a diff for user-data leaks, such as raw text() SQL without :uid, new tables with user_id that test_isolation.py doesn't cover, or prefixes missing from MODULE_OF_PATH.
11. pg-tester: runs the suite on SQLite and on PostgreSQL, like CI, and reports failures that only happen on one database.

Phase 4: Skills / slash commands (.claude/skills/)

12. /new-migration, /new-route, /new-card-parser: step-by-step recipes that hand off to the matching subagent.
13. /check-all: runs the full CI sequence locally (both databases, typecheck, build).
14. /feature <description>: plan → implement → isolation-reviewer → /code-review → commit on a branch.

Phase 5: Parallel work in worktrees

15. Run independent tasks (say, a parser and a dashboard change) as agents in separate git worktrees.
16. Pitfall specific to this repo: venv_expense/, node_modules/ and .env.local are git-ignored, so a new worktree has none of them. A WorktreeCreate-style setup step or skill should point at the main checkout's venv by absolute path and run pnpm install.
17. Merge one branch at a time, and run /check-all after each merge.

Phase 6: CI and review

18. Optionally add the Claude GitHub Action so @claude can be asked on PRs to run the isolation and migration review.
19. Keep the existing CI as the final check. Agents must get it green, not skip it.
