"""A Session for tests that still write plain SQL with `?` placeholders.

`test_db()` is a real SQLAlchemy Session on the test database (SQLite or PostgreSQL, whichever conftest chose), so
it can be handed to code that takes a Session. Its `execute()` also accepts an SQL string with positional `?`
parameters, and the rows it returns allow both `row[0]` and `row["name"]`, like sqlite3.Row did.
"""
import re

from sqlalchemy import text
from sqlalchemy.orm import Session


class Row(tuple):
    def __new__(cls, values, keys):
        r = super().__new__(cls, values)
        r._keys = keys
        return r

    def __getitem__(self, k):
        if isinstance(k, str):
            return tuple.__getitem__(self, self._keys.index(k))
        return tuple.__getitem__(self, k)

    def keys(self):
        return list(self._keys)


class _Result:
    def __init__(self, result):
        self._r = result
        self._keys = list(result.keys()) if result.returns_rows else []

    def _row(self, r):
        return None if r is None else Row(tuple(r), self._keys)

    def fetchone(self):
        return self._row(self._r.fetchone())

    def fetchall(self):
        return [self._row(r) for r in self._r.fetchall()]

    def __iter__(self):
        return (self._row(r) for r in self._r)

    @property
    def rowcount(self):
        return self._r.rowcount


def _named(sql, params):
    """`?` placeholders and a tuple of values -> `:p0`.. and a dict."""
    if params is None:
        return sql, {}
    if isinstance(params, dict):
        return sql, params
    counter = iter(range(len(params)))
    return re.sub(r"\?", lambda m: f":p{next(counter)}", sql), {f"p{i}": v for i, v in enumerate(params)}


class TestSession(Session):
    __test__ = False  # not a test class for pytest

    def execute(self, statement, params=None, *args, **kwargs):
        if isinstance(statement, str):
            sql, bound = _named(statement, params)
            return _Result(super().execute(text(sql), bound, *args, **kwargs))
        return super().execute(statement, params, *args, **kwargs)


def test_db():
    from db.engine import engine
    return TestSession(engine, autoflush=False, expire_on_commit=False)


test_db.__test__ = False
