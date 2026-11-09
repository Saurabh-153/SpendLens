"""Sign-in, login sessions and per-user module access.

Every /spendlens/api route passes through `guard` (a dependency on the combined router in routes/api.py). It reads the
session cookie and maps the URL to the module it belongs to (`MODULE_OF_PATH`), so the backend alone decides who
may call what - the frontend's locked tabs are only a courtesy. Admins have every module.
"""
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, Request

from db.base import utc_now_text
from db.ddl import sync_sequences
from db.engine import SessionLocal, get_session
from db.models import AccessRequest, AuthSession, ModuleGrant, User

COOKIE = "sl_session"
SESSION_DAYS = 30
API = "/spendlens/api"

# The modules an admin can switch on per user. Dashboard is always on; Admin is admin-only.
MODULES = [
    {"id": "expense", "label": "Expense", "description": "Expenses, budgets, categories, reminders, calendar and day trackers"},
    {"id": "holdings", "label": "Holdings", "description": "Portfolio, holdings, SIPs and price updates"},
    {"id": "ledger", "label": "Ledger", "description": "Stock ledger from broker tradebooks: dividends, XIRR, realised gains and reconciliation"},
    {"id": "cards", "label": "Cards", "description": "Credit cards, statements and the card advisor"},
]
MODULE_IDS = [m["id"] for m in MODULES]

# First path segment after /spendlens/api -> module. Anything not listed needs a signed-in user and nothing more.
MODULE_OF_PATH = {
    "budget": "expense", "categories": "expense", "subcategories": "expense", "expenses": "expense", "dashboard": "expense",
    "export": "holdings", "forecast": "expense", "reminder-categories": "expense", "reminders": "expense",
    "calendar.ics": "expense", "vacations": "expense", "trackers": "expense",
    "holding-columns": "holdings", "holding-groups": "holdings", "holdings": "holdings", "portfolio": "holdings",
    "prices": "holdings", "sip-log": "holdings", "mf": "holdings",
    "transactions": "ledger", "ledger": "ledger", "equity": "ledger",
    "cards": "cards",
}
PUBLIC = {"healthz", "auth/login", "auth/logout", "auth/reset-local"}   # reset-local refuses anything not from this computer
ADMIN_ONLY = {"database", "admin"}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _expiry_text(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def start_session(session, user: User) -> str:
    """A new login for `user`. Returns the cookie value; only its hash is stored."""
    token = secrets.token_urlsafe(32)
    session.add(AuthSession(token_hash=_token_hash(token), user_id=user.id, expires_at=_expiry_text(SESSION_DAYS)))
    session.commit()
    return token


def end_session(session, token: str | None):
    if token:
        session.query(AuthSession).filter(AuthSession.token_hash == _token_hash(token)).delete()
        session.commit()


def user_for_token(session, token: str | None) -> User | None:
    if not token:
        return None
    s = session.get(AuthSession, _token_hash(token))
    if not s or s.expires_at < utc_now_text():
        return None
    u = session.get(User, s.user_id)
    return u if u and u.is_active else None


def enabled_modules(session, user: User) -> list[str]:
    if user.role == "admin":
        return list(MODULE_IDS)
    rows = session.query(ModuleGrant.module).filter(ModuleGrant.user_id == user.id).all()
    have = {r[0] for r in rows}
    return [m for m in MODULE_IDS if m in have]


def pending_count(session) -> int:
    return session.query(AccessRequest).filter(AccessRequest.status == "pending").count()


def _route_key(path: str) -> str:
    return path[len(API):].lstrip("/") if path.startswith(API) else path.lstrip("/")


def guard(request: Request, session=Depends(get_session)):
    """Sign-in and module check for every API route; see the module docstring."""
    key = _route_key(request.url.path)
    if key in PUBLIC:
        return
    user = user_for_token(session, request.cookies.get(COOKIE))
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    request.state.user = user
    session.info["user_id"] = user.id   # from here every ORM query on this request sees only this user's rows (db/scope.py)
    first = key.split("/", 1)[0]
    if first in ADMIN_ONLY:
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="Only an admin can do that.")
        return
    module = MODULE_OF_PATH.get(first)
    if module and module not in enabled_modules(session, user):
        raise HTTPException(status_code=403, detail=f"The {module} module is not enabled for your account.",
                            headers={"X-Module": module})


def current_user(request: Request) -> User:
    """The signed-in user; only valid on routes that `guard` has already let through."""
    return request.state.user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only an admin can do that.")
    return user


# ---------------------------------------------------------------- password reset from the sign-in page

_RESET_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I/L: read off the console and typed in
_reset_code = None


def reset_code(rotate: bool = False) -> str:
    """The one-time code the sign-in page's "Forgot password?" form asks for. It exists only in this process and is
    printed to the console that started the backend, so knowing it proves you are at that computer."""
    global _reset_code
    if _reset_code is None or rotate:
        _reset_code = "".join(secrets.choice(_RESET_ALPHABET) for _ in range(8))
    return _reset_code


def check_reset_code(code: str) -> bool:
    return secrets.compare_digest((code or "").strip().upper().replace("-", "").replace(" ", ""), reset_code())


def announce_reset_code():
    c = reset_code()
    print(f"[spendlens] Password reset code for the sign-in page (Forgot password?): {c[:4]}-{c[4:]}", flush=True)


ADMIN_PASSWORD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "first-admin-password.txt")


def bootstrap_admin():
    """First start: create the admin that owns the existing data (id 1, since every row so far is user_id=1).
    SPENDLENS_ADMIN_EMAIL / SPENDLENS_ADMIN_PASSWORD choose the login; without a password a random one is written to
    the git-ignored first-admin-password.txt (SPENDLENS_ADMIN_PASSWORD_FILE overrides), never to the console log."""
    session = SessionLocal()
    try:
        if session.query(User).count():
            return
        email = (os.environ.get("SPENDLENS_ADMIN_EMAIL") or "admin@spendlens.local").strip().lower()
        password = os.environ.get("SPENDLENS_ADMIN_PASSWORD")
        generated = not password
        if generated:
            password = secrets.token_urlsafe(12)
        session.add(User(id=1, email=email, name="Admin", password_hash=hash_password(password), role="admin"))
        session.commit()
        sync_sequences(session.connection(), ["users"])  # the id was explicit; PostgreSQL's counter must move past it
        session.commit()
        if generated:
            path = os.environ.get("SPENDLENS_ADMIN_PASSWORD_FILE") or ADMIN_PASSWORD_FILE
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"SpendLens admin: {email}\nPassword: {password}\nSign in, change the password, then delete this file.\n")
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            print(f"[spendlens] Created admin {email}; the password is in {path} - sign in, change it, delete the file.", flush=True)
    finally:
        session.close()
