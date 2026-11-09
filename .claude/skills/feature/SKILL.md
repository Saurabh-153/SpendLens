---
name: feature
description: Build a SpendLens feature end to end - plan, implement (delegating schema, routes and parsers to the specialist subagents), isolation review, code review, full checks, and a commit on a feature branch. User-invoked only, because it commits.
argument-hint: <the feature, in a sentence or two>
disable-model-invocation: true
---

Feature: **$ARGUMENTS**

## 1. Plan (stop for approval)

Read what the feature touches (CLAUDE.md's architecture section says where things live). Write a short plan:
- what the user will see, and which module it belongs to (expense / holdings / ledger / cards / admin);
- schema changes, endpoints (method + path), UI components, tests;
- what is out of scope.

Show the plan and **wait for the user's go-ahead** unless they already said to proceed without asking. Ask about
real choices (behaviour, data shape) here, not halfway through.

## 2. Branch

`git branch --show-current`. If on `main`, create `feature/<short-slug>` from it. If already on a feature branch,
ask whether to build on it or branch off. **The working tree may hold the user's own uncommitted work** (check
`git status`). Never stash, reset, or check it out, and record which files are dirty *before* you start, so the
commit in step 6 includes only what this feature changed.

## 3. Implement, in dependency order

1. Schema: the **migration-author** subagent (or `/new-migration`). It lands first.
2. Endpoints: the **route-builder** subagent, one call per coherent group of endpoints.
3. A bank statement format: the **card-parser** subagent.
4. UI (`artifacts/spendlens/src/`) and glue: do it yourself, in the style of the neighbouring components, using the
   `api.ts` functions the route-builder added.

Give each subagent the plan's relevant part and the outputs of the earlier steps. Check each report before
starting the next step.

## 4. Review

- The **isolation-reviewer** subagent on the full diff. Fix its findings.
- The `/code-review` skill on the diff. Fix the correctness findings. List the rest for the user.

## 5. Checks

`/check-all` (full). Everything must pass. If PostgreSQL couldn't run, say so in the summary: CI will run it.

## 6. Commit (local only)

Stage only the files this feature changed. Use `git add <paths>`, never `git add -A` or `.`, and leave out files
that were already dirty in step 2 unless the feature edited them, in which case ask. Commit message: a single
imperative summary line in the style of `git log --oneline -10`, a blank line, a few lines on why, and the
attribution trailer from the session's instructions. Don't push. Pushing and PRs are the user's call.

## 7. Report

What was built, files changed, review findings fixed and left open, the check table, and the commit hash.
