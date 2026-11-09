---
name: parallel
description: Run several independent SpendLens tasks at once, each in its own git worktree via a background subagent, then merge their branches back one at a time with checks after each merge. User-invoked only, because it creates branches and merges them.
argument-hint: <task 1>; <task 2>; ...   (independent tasks, separated by semicolons)
disable-model-invocation: true
---

Tasks: **$ARGUMENTS**

## 0. Preconditions (stop if they fail)

- `git status --short` must be clean, apart from untracked files that don't matter to the tasks. Worktrees branch from
  the current **commit** (`worktree.baseRef: head` in `.claude/settings.json`), so uncommitted work isn't in them, and
  merging back into a dirty tree can conflict with it. If it's dirty, tell the user what's uncommitted and stop. Don't
  commit, stash or reset their work yourself.
- Note the current branch: everything merges back into it.

## 1. Split, and check the tasks really are independent

For each task, list the files it will likely touch. Then apply these rules, and say what you decided:
- **At most one task that changes the schema per batch.** Two new Alembic revisions written in parallel both point at
  the same `down_revision` and leave two heads. Run schema tasks one after another.
- Tasks that edit the same component or module: run them one after another.
- Tasks that each add to `src/api.ts` or `tests/test_api_shape.py` may run in parallel. Expect small append-only
  conflicts there, and resolve them by keeping both sides.
- More than 4 tasks: ask whether to run them in batches.

Show the plan (task → agent type → files) and wait for the user's go-ahead.

## 2. Launch

For each task, call the Agent tool with `isolation: "worktree"` and `run_in_background: true`. Use the matching agent
type (`migration-author`, `route-builder`, `card-parser`, otherwise general-purpose). Start every prompt with these
rules, because subagents may not get the worktree session hook:

> You are working in a git worktree, not the main checkout. First run `pnpm install --frozen-lockfile --prefer-offline`
> if `artifacts/spendlens/node_modules` is missing. There is no `venv_expense/` here: use the main checkout's
> `<main checkout>\venv_expense\Scripts\python.exe` for pytest, ruff and alembic. Don't run PostgreSQL tests
> (`SPENDLENS_TEST_PG` / `TEST_DATABASE_URL`): every run wipes the one shared `_test` database. SQLite tests are safe.
> Don't start the app on port 5000. When the task's tests and `pnpm run typecheck` pass, commit on this worktree's
> branch (one imperative summary line, a blank line, why, and the attribution trailer) and report the branch name,
> the worktree path, the files changed and the test output.

Fill in the main checkout's absolute path. Then tell the user what's running, and wait for the completion
notifications. Never guess at a result that hasn't arrived.

## 3. Merge back, one branch at a time

For each finished task, in the order that minimises conflicts (schema first, then routes, then UI):
1. Read its report. If it didn't commit, or its tests failed, leave the branch alone and report it.
2. `git merge --no-ff <branch> -m "Merge <branch>: <task>"`.
3. Conflicts: resolve append-only ones in `api.ts` / `test_api_shape.py` by keeping both sides. For anything else,
   `git merge --abort` and ask the user.
4. Two Alembic heads after a merge (`alembic heads` lists more than one): stop and use `/new-migration` to write a
   merge revision. Don't hand-edit `down_revision` in a committed file.
5. `/check-all quick` before merging the next branch.

## 4. Finish

- `/check-all` (full) once everything is merged. This is the only PostgreSQL run, here in the main checkout.
- The **isolation-reviewer** subagent on the combined diff (`git diff <start commit>..HEAD`) if any task touched
  routes, models, migrations or `cards.py`.
- Clean up each merged worktree with
  `python .claude/scripts/worktree_remove.py <worktree path>`. It deletes the worktree's `node_modules` first, since
  `git worktree remove` fails on them on Windows, and it deletes the branch only when it's merged.
- Don't push.

## 5. Report

A table of task → branch → merged / not merged (why) → checks. Then the full `/check-all` result, review findings,
and any worktrees or branches left behind.
