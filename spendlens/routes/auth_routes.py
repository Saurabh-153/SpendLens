"""Sign-in, the signed-in user's modules and access requests, and the admin side: users, per-user modules and the
approval queue. `auth.guard` has already checked the session (and `admin` paths are admin-only) before these run.
"""
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

import auth
import security
from db.base import row_dict, utc_now_text
from db.engine import get_session
from db.user_defaults import seed_user
from db.models import AccessRequest, AuthSession, ModuleGrant, User

router = APIRouter(prefix="/spendlens/api", tags=["auth"])


def _bad(msg, status=400):
    raise HTTPException(status_code=status, detail=msg)


def _public_user(u: User):
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "is_active": u.is_active, "created_at": u.created_at}


def _me(session, user: User):
    mine = (session.query(AccessRequest).filter(AccessRequest.user_id == user.id)
            .order_by(AccessRequest.id.desc()).all())
    return {
        **_public_user(user),
        "modules": auth.enabled_modules(session, user),
        "all_modules": auth.MODULES,
        "requests": [row_dict(r) for r in mine],
        "pending_requests": auth.pending_count(session) if user.role == "admin" else 0,
    }


class LoginRequest(BaseModel):
    email: str
    password: str


def secure_cookie(request: Request) -> bool:
    """The session cookie is sent over HTTPS only when the app is reached over HTTPS (directly, or behind a local
    reverse proxy that sets X-Forwarded-Proto), or when SPENDLENS_SECURE_COOKIE=1 says it always is."""
    return request.url.scheme == "https" or os.environ.get("SPENDLENS_SECURE_COOKIE") == "1"


def _too_many(seconds):
    minutes = max(1, round(seconds / 60))
    raise HTTPException(status_code=429, detail=f"Too many failed attempts. Try again in about {minutes} minute{'s' if minutes > 1 else ''}.",
                        headers={"Retry-After": str(seconds)})


@router.post("/auth/login")
def login(data: LoginRequest, request: Request, response: Response, session=Depends(get_session)):
    email = data.email.strip().lower()
    ip = security.client_ip(request)
    wait = max(security.LOGIN.retry_after((ip, email)), security.LOGIN_PER_IP.retry_after(ip))
    if wait:
        _too_many(wait)
    user = session.query(User).filter(User.email == email).first()
    # The same message for an unknown email and a wrong password, so the form does not reveal which accounts exist.
    if not user or not user.is_active or not auth.check_password(data.password, user.password_hash):
        security.LOGIN.fail((ip, email))
        security.LOGIN_PER_IP.fail(ip)
        _bad("Wrong email or password.", 401)
    security.LOGIN.clear((ip, email))
    token = auth.start_session(session, user)
    response.set_cookie(auth.COOKIE, token, max_age=auth.SESSION_DAYS * 86400, httponly=True, samesite="lax", path="/",
                        secure=secure_cookie(request))
    return _me(session, user)


LOCAL_HOSTS = {"127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost"}   # the last but one: Node's dev proxy on IPv4


def is_local_request(request: Request) -> bool:
    """True only for a browser on the computer running SpendLens: the connection comes from loopback and no proxy
    says it forwarded the request from somewhere else."""
    host = request.client.host if request.client else ""
    if host not in LOCAL_HOSTS:
        return False
    fwd = request.headers.get("x-forwarded-for", "") + "," + request.headers.get("x-real-ip", "")
    hops = [h.strip() for h in fwd.split(",") if h.strip()]
    return all(h in LOCAL_HOSTS for h in hops) and not request.headers.get("forwarded")


class LocalReset(BaseModel):
    email: str
    new_password: str
    code: str = ""


@router.post("/auth/reset-local")
def reset_local(data: LocalReset, request: Request, session=Depends(get_session)):
    """Forgotten password, from the sign-in page: allowed only on the computer running SpendLens and with the one-time
    code the backend printed to its console (auth.reset_code), which is no more than someone at that computer could
    already do with `python spendlens/reset_password.py`. The code proves it: a request relayed from another machine
    by a local proxy looks like loopback, but its sender cannot read the console. A used code is replaced."""
    if not is_local_request(request):
        _bad("Password reset works only on the computer running SpendLens. Ask an admin to reset it in Admin › Users.", 403)
    ip = security.client_ip(request)
    wait = security.RESET.retry_after(ip)
    if wait:
        _too_many(wait)
    if not auth.check_reset_code(data.code):
        security.RESET.fail(ip)
        _bad("Wrong reset code. It is printed in the window where the SpendLens backend is running.", 403)
    if len(data.new_password) < 8:
        _bad("Use at least 8 characters.")
    user = session.query(User).filter(User.email == data.email.strip().lower()).first()
    if user is None:
        _bad("No account with that email.", 404)
    user.password_hash = auth.hash_password(data.new_password)
    session.query(AuthSession).filter(AuthSession.user_id == user.id).delete(synchronize_session=False)
    session.commit()
    security.RESET.clear(ip)
    auth.reset_code(rotate=True)
    auth.announce_reset_code()
    return {"ok": True}


@router.post("/auth/logout")
def logout(request: Request, response: Response, session=Depends(get_session)):
    auth.end_session(session, request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE, path="/", httponly=True, samesite="lax", secure=secure_cookie(request))
    return {"ok": True}


@router.get("/auth/me")
def me(user: User = Depends(auth.current_user), session=Depends(get_session)):
    return _me(session, user)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@router.post("/auth/password")
def change_password(data: PasswordChange, request: Request, user: User = Depends(auth.current_user), session=Depends(get_session)):
    if not auth.check_password(data.current_password, user.password_hash):
        _bad("Current password is wrong.")
    if len(data.new_password) < 8:
        _bad("Use at least 8 characters.")
    user.password_hash = auth.hash_password(data.new_password)
    # every other sign-in of this user ends (a stolen session dies with the old password); this one stays
    this = auth._token_hash(request.cookies.get(auth.COOKIE) or "")
    session.query(AuthSession).filter(AuthSession.user_id == user.id, AuthSession.token_hash != this).delete(
        synchronize_session=False)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------- access requests (any signed-in user)

class AccessRequestIn(BaseModel):
    module: str
    note: str = ""


@router.post("/access/requests", status_code=201)
def raise_request(data: AccessRequestIn, user: User = Depends(auth.current_user), session=Depends(get_session)):
    if data.module not in auth.MODULE_IDS:
        _bad("Unknown module.")
    if data.module in auth.enabled_modules(session, user):
        _bad("That module is already enabled for you.", 409)
    pending = session.query(AccessRequest).filter(AccessRequest.user_id == user.id, AccessRequest.module == data.module,
                                                  AccessRequest.status == "pending").first()
    if pending:
        _bad("You already have a pending request for that module.", 409)
    r = AccessRequest(user_id=user.id, module=data.module, note=data.note.strip()[:500])
    session.add(r)
    session.commit()
    return row_dict(r)


@router.get("/access/requests")
def my_requests(user: User = Depends(auth.current_user), session=Depends(get_session)):
    rows = session.query(AccessRequest).filter(AccessRequest.user_id == user.id).order_by(AccessRequest.id.desc()).all()
    return [row_dict(r) for r in rows]


# ---------------------------------------------------------------- admin: approval queue

def _request_view(r: AccessRequest, users: dict):
    u = users.get(r.user_id)
    return {**row_dict(r), "user_email": u.email if u else "", "user_name": u.name if u else ""}


@router.get("/admin/access/requests")
def admin_requests(status: str | None = None, session=Depends(get_session)):
    q = session.query(AccessRequest)
    if status:
        q = q.filter(AccessRequest.status == status)
    rows = q.order_by(AccessRequest.id.desc()).limit(500).all()
    users = {u.id: u for u in session.query(User).filter(User.id.in_({r.user_id for r in rows})).all()} if rows else {}
    return [_request_view(r, users) for r in rows]


class Decision(BaseModel):
    note: str = ""


def _decide(rid: int, approve: bool, note: str, admin: User, session):
    r = session.get(AccessRequest, rid)
    if not r:
        _bad("Request not found.", 404)
    if r.status != "pending":
        _bad(f"This request was already {r.status}.", 409)
    if approve and not session.query(ModuleGrant).filter(ModuleGrant.user_id == r.user_id, ModuleGrant.module == r.module).first():
        session.add(ModuleGrant(user_id=r.user_id, module=r.module, granted_by=admin.id))
    r.status = "approved" if approve else "rejected"
    r.decided_by, r.decided_at, r.decision_note = admin.id, utc_now_text(), note.strip()[:500]
    session.commit()  # the grant and the decision land together
    return _request_view(r, {u.id: u for u in session.query(User).filter(User.id == r.user_id)})


@router.post("/admin/access/requests/{rid}/approve")
def approve_request(rid: int, data: Decision = Decision(), admin: User = Depends(auth.require_admin), session=Depends(get_session)):
    return _decide(rid, True, data.note, admin, session)


@router.post("/admin/access/requests/{rid}/reject")
def reject_request(rid: int, data: Decision = Decision(), admin: User = Depends(auth.require_admin), session=Depends(get_session)):
    return _decide(rid, False, data.note, admin, session)


# ---------------------------------------------------------------- admin: users and their modules

def _user_row(session, u: User):
    return {**_public_user(u), "modules": auth.enabled_modules(session, u)}


@router.get("/admin/users")
def list_users(session=Depends(get_session)):
    users = session.query(User).order_by(User.id).all()
    grants = {}
    for g in session.query(ModuleGrant).all():
        grants.setdefault(g.user_id, set()).add(g.module)
    pending = {}
    for r in session.query(AccessRequest).filter(AccessRequest.status == "pending"):
        pending.setdefault(r.user_id, []).append(r.module)
    return {
        "modules": auth.MODULES,
        "users": [{**_public_user(u),
                   "modules": auth.MODULE_IDS if u.role == "admin" else [m for m in auth.MODULE_IDS if m in grants.get(u.id, set())],
                   "pending": pending.get(u.id, [])} for u in users],
    }


class UserCreate(BaseModel):
    email: str
    name: str = ""
    password: str
    role: str = "user"
    modules: list[str] = []


def _clean_modules(modules):
    bad = [m for m in modules if m not in auth.MODULE_IDS]
    if bad:
        _bad(f"Unknown module: {bad[0]}")
    return [m for m in auth.MODULE_IDS if m in set(modules)]


@router.post("/admin/users", status_code=201)
def create_user(data: UserCreate, admin: User = Depends(auth.require_admin), session=Depends(get_session)):
    email = data.email.strip().lower()
    if "@" not in email:
        _bad("Enter a valid email.")
    if len(data.password) < 8:
        _bad("Use at least 8 characters for the password.")
    if data.role not in ("admin", "user"):
        _bad("Role must be admin or user.")
    modules = _clean_modules(data.modules)
    u = User(email=email, name=data.name.strip(), password_hash=auth.hash_password(data.password), role=data.role)
    session.add(u)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        _bad("A user with that email already exists.", 409)
    session.add_all([ModuleGrant(user_id=u.id, module=m, granted_by=admin.id) for m in modules])
    session.commit()
    seed_user(u.id)  # default categories, budget and reminder categories, so the new person has a working app
    return _user_row(session, u)


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None


@router.patch("/admin/users/{uid}")
def update_user(uid: int, data: UserUpdate, admin: User = Depends(auth.require_admin), session=Depends(get_session)):
    u = session.get(User, uid)
    if not u:
        _bad("User not found.", 404)
    if uid == admin.id and (data.role == "user" or data.is_active is False):
        _bad("You cannot remove your own admin access or deactivate yourself.", 409)
    if data.name is not None:
        u.name = data.name.strip()
    if data.role is not None:
        if data.role not in ("admin", "user"):
            _bad("Role must be admin or user.")
        u.role = data.role
    if data.password is not None:
        if len(data.password) < 8:
            _bad("Use at least 8 characters for the password.")
        u.password_hash = auth.hash_password(data.password)
        session.query(AuthSession).filter(AuthSession.user_id == uid).delete()  # a reset signs the user out everywhere
    if data.is_active is not None:
        u.is_active = data.is_active
        if not data.is_active:
            session.query(AuthSession).filter(AuthSession.user_id == uid).delete()
    session.commit()
    return _user_row(session, u)


class ModulesIn(BaseModel):
    modules: list[str]


@router.put("/admin/users/{uid}/modules")
def set_modules(uid: int, data: ModulesIn, admin: User = Depends(auth.require_admin), session=Depends(get_session)):
    u = session.get(User, uid)
    if not u:
        _bad("User not found.", 404)
    want = set(_clean_modules(data.modules))
    have = {g.module: g for g in session.query(ModuleGrant).filter(ModuleGrant.user_id == uid)}
    for m, g in have.items():
        if m not in want:
            session.delete(g)  # revoking only locks the module; the user's data stays
    for m in want - set(have):
        session.add(ModuleGrant(user_id=uid, module=m, granted_by=admin.id))
        # a direct grant answers any open request for it
        for r in session.query(AccessRequest).filter(AccessRequest.user_id == uid, AccessRequest.module == m,
                                                     AccessRequest.status == "pending"):
            r.status, r.decided_by, r.decided_at, r.decision_note = "approved", admin.id, utc_now_text(), "Enabled by an admin"
    session.commit()
    return _user_row(session, u)
