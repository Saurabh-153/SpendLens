---
name: check-all
description: Run SpendLens's full CI sequence locally - pytest on SQLite, pytest on PostgreSQL, typecheck, build, plus ruff - and report a pass/fail table with diagnosed failures. Use before committing, after merging a branch, or to reproduce a CI failure.
argument-hint: "[quick]  (quick = only tests for changed files, both databases, plus typecheck)"
---

Run the checks CI runs (`.github/workflows/ci.yml`), plus lint. Mode: **$ARGUMENTS** (empty = full).

1. Hand the run to the **pg-tester** subagent with the Agent tool, so the long test output stays out of this
   conversation. Tell it the mode. For `quick`, give it the changed Python files from
   `git diff --name-only HEAD` and `git status --short` so it picks the matching tests.
2. While it runs, lint the tree yourself:
   `.\venv_expense\Scripts\python -m ruff check .` (config in `ruff.toml`). CI doesn't run ruff yet, so findings are
   advisory. List them, don't fix them unless asked.
3. Report one table:

   | Check | Result | Time |
   |---|---|---|
   | pytest (SQLite) | pass / N failed | |
   | pytest (PostgreSQL) | pass / N failed / skipped: reason | |
   | typecheck | | |
   | build | | |
   | ruff | clean / N findings | |

   Then the failures grouped by cause, from pg-tester's diagnosis. A skipped PostgreSQL run is not a pass. Say so
   plainly, since CI will run it.
4. Don't fix anything as part of this skill. If the user wants fixes, that's a follow-up.
