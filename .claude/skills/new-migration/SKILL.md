---
name: new-migration
description: Make a SpendLens schema change (new table, column, index or constraint) as a model change plus an Alembic revision that runs on SQLite and PostgreSQL, proven on scratch databases. Hands the work to the migration-author subagent.
argument-hint: <what the schema change is, e.g. "add notes column to holdings">
---

Schema change requested: **$ARGUMENTS**

1. If the request is empty or ambiguous about the shape (table vs column, nullable, default, which existing rows get
   which value, per-user or shared), ask the user before starting. These decisions are hard to undo once the
   migration has run on their real data.
2. Find what the change touches: the model in `spendlens/db/models/`, the routes and modules reading it
   (`Grep` the table/column name), and `alembic heads` (`.\venv_expense\Scripts\python -m alembic heads`) to know the
   current head. Note whether the table is user-owned.
3. Hand the work to the **migration-author** subagent with the Agent tool. Give it: the change, the model file, the
   current head revision, whether the data is per-user, what existing rows should get, and the code that reads the
   table. Ask for its report in its own format.
4. When it reports back, check its claims yourself:
   - the new file in `alembic/versions/` has a real `downgrade()` and `down_revision` = the old head;
   - it ran upgrade -> downgrade -> upgrade on a scratch copy **and** on a fresh path (look for the commands and their
     output in its report, not just "it passed");
   - PostgreSQL was run, or it says clearly why not.
5. If the table is user-owned or the change touches routes, run the **isolation-reviewer** subagent on the diff.
6. Tell the user: the revision id, what it changes, what was tested on which database, and that the next start of
   `app.py` will apply it to their real database. That step is theirs to run.
