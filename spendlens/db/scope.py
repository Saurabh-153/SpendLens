"""Per-user data scoping for the ORM.

A session whose `info["user_id"]` is set (auth.guard does that for every signed-in request) sees only that user's rows:
every ORM SELECT / UPDATE / DELETE on a model with a `user_id` column gets `user_id = <that user>` added, and every new
row is stamped with that user's id, whatever the request body said. So a route written for one user cannot read or
change another's data by forgetting a filter or guessing an id.

A session without it (the price scheduler, start-up, tests that talk to the database directly) is not filtered.
Raw SQL (`text()`) is not covered; the cards module writes its own `user_id` conditions.
"""
from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from .base import Base

# Tables that hold users and sign-ins themselves: the admin screens read every user's rows from these.
NOT_SCOPED = {"users", "auth_sessions", "module_grants", "access_requests"}

_scoped = None


def scoped_models():
    """The mapped classes that carry a `user_id` (cached once all models are imported)."""
    global _scoped
    if _scoped is None:
        _scoped = tuple(m.class_ for m in Base.registry.mappers
                        if "user_id" in m.local_table.c and m.local_table.name not in NOT_SCOPED)
    return _scoped


def user_of(session, default=1):
    """The user a session is scoped to, or `default` for an unscoped one (code written for the single-user app)."""
    uid = session.info.get("user_id")
    return default if uid is None else uid


@event.listens_for(Session, "do_orm_execute")
def _filter_to_user(state):
    uid = state.session.info.get("user_id")
    if uid is None or not (state.is_select or state.is_update or state.is_delete):
        return
    options = [with_loader_criteria(cls, cls.user_id == uid, include_aliases=True, track_closure_variables=False)
               for cls in scoped_models()]
    state.statement = state.statement.options(*options)


@event.listens_for(Session, "before_flush")
def _stamp_user(session, flush_context, instances):
    uid = session.info.get("user_id")
    if uid is None:
        return
    scoped = scoped_models()
    for obj in session.new:
        if isinstance(obj, scoped):
            obj.user_id = uid
