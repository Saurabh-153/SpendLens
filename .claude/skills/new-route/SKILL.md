---
name: new-route
description: Add or change a SpendLens /spendlens/api endpoint end to end - route, module access (auth.MODULE_OF_PATH), per-user scoping, the typed client in src/api.ts, and shape/isolation tests. Hands the work to the route-builder subagent, after a migration if the schema must change.
argument-hint: <METHOD /path - what it does, e.g. "GET /holdings/{id}/history - value over time">
---

Endpoint requested: **$ARGUMENTS**

1. Pin down the contract before any code: method and path, request body, response keys and types, which module it
   belongs to (expense / holdings / ledger / cards, or admin-only), and what a missing or foreign id returns. If the
   request leaves any of that open and the code doesn't settle it, ask the user.
2. Read the domain's router (`spendlens/routes/<domain>_routes.py`), its section of `artifacts/spendlens/src/api.ts`,
   and `auth.MODULE_OF_PATH`. Decide whether the schema must change.
3. **Schema change needed?** Run `/new-migration` first (or the migration-author subagent directly) and wait for
   it. Routes come after the schema they read.
4. Hand the endpoint to the **route-builder** subagent with the Agent tool. Give it the contract from step 1, the
   router file, the module, and any new columns from step 3.
5. When it reports back, verify:
   - the first path segment is in `MODULE_OF_PATH` (or `ADMIN_ONLY`);
   - `api.ts` has the type and the call, and the type's keys match the returned dict;
   - a new read endpoint is in `READ_ENDPOINTS` in `tests/test_api_shape.py`;
   - user-owned data has a `tests/test_isolation.py` case.
6. Run the **isolation-reviewer** subagent on the diff. Fix what it finds, or report it if it's a design question.
7. Tell the user: endpoints, files changed, tests added and their output, and any UI that still needs to call the
   new client function.
