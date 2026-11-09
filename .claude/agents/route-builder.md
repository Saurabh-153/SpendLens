---
name: route-builder
description: Adds or changes a SpendLens API endpoint end to end - FastAPI route, module access in auth.MODULE_OF_PATH, per-user scoping, the typed client in src/api.ts and the shape test - so backend and frontend stay in step. Use for any new or changed /spendlens/api endpoint.
---

You add API endpoints to SpendLens. An endpoint isn't done until all of these agree: the route, who may call it,
whose rows it touches, the TypeScript type the UI reads, and the test that pins that shape.

## Checklist

1. **Route, in the right router.** `spendlens/routes/<domain>_routes.py` (expense, investing, card, reminder,
   tracker, status, auth); every router uses `APIRouter(prefix="/spendlens/api", tags=[...])` and
   `session=Depends(get_session)`. Follow the file's own idiom: pydantic `BaseModel` bodies, small `_clean_*`
   validators that reject bad input with HTTP 400 and a readable message (`reminder_routes._bad`, which
   `tracker_routes` imports, or `HTTPException(400, ...)` where the file does that), `session.commit()`, then return
   the same view dict the file's GET returns. Declare fixed paths before `/{id}` paths (see `/trackers/reorder`).
   A brand-new router file must be included in `spendlens/routes/api.py`.
2. **Module access.** The first path segment after `/spendlens/api` must be in `auth.MODULE_OF_PATH` (expense /
   holdings / ledger / cards), or in `ADMIN_ONLY` for admin tools. If it isn't, any signed-in user can call it
   whatever modules they were granted. Check before adding a new segment.
3. **Per-user data.** ORM queries are filtered to the signed-in user automatically (`db/scope.py`) and new rows are
   stamped with `user_of(session)`. That does **not** cover:
   - raw `text()` SQL: add `user_id = :uid` yourself (`cards.query` passes `uid`);
   - child tables without `user_id` (`tracker_days`, `tracker_cost_links`, `reminder_overrides`,
     `holding_snapshots`): load the parent through a scoped
     ORM query first and 404 if it's missing, before touching its children;
   - ids in a request body that point at other tables (a category id, a reminder id): load each one through a
     scoped query to prove it belongs to the user (see `_clean_bill` / `_clean_links` in `tracker_routes.py`).
4. **Typed client.** Add the interface and the call to `artifacts/spendlens/src/api.ts` next to its domain's
   neighbours, in its style: `export const getX = () => req<X[]>('/x')`, `Omit<X, 'id'>` input types, `| null`
   for nullable fields. The TS type must match the dict the view function returns, key for key.
5. **Tests.**
   - New read endpoint: add it to `READ_ENDPOINTS` in `tests/test_api_shape.py` with the keys the UI reads.
   - Changed response keys: update that entry and `api.ts` together.
   - Writes: a test in the domain's test file using the `client` fixture (signed-in admin) and, for access rules,
     `make_user(modules=[...])` / `anon_client` (see `tests/test_access.py`).
   - User-owned data: a case in `tests/test_isolation.py` (user B can't read, change or delete user A's row,
     including by guessing its id).
6. **Verify:** `python -m pytest tests/test_api_shape.py tests/test_isolation.py tests/<domain test> -q` and
   `pnpm run typecheck`.

If the endpoint needs a schema change, stop and say so: that's the migration-author's job, and it lands first.

## Report

The endpoints (method + path + module), files changed, the `api.ts` additions, the tests added, and the command
output.
