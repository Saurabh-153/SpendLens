"""Who can sign in and which modules each person has: users, login sessions, module grants and the
access requests a user raises for an admin to approve. A grant row means the module is enabled.
"""
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, utc_now_text


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str] = mapped_column(default="")
    password_hash: Mapped[str]
    role: Mapped[str] = mapped_column(default="user")  # 'admin' / 'user'
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[str] = mapped_column(default=utc_now_text)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(primary_key=True)  # sha256 of the cookie value; the cookie itself is never stored
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=utc_now_text)


class ModuleGrant(Base):
    __tablename__ = "module_grants"
    __table_args__ = (UniqueConstraint("user_id", "module"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    module: Mapped[str]  # one of access.MODULES
    granted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)
    granted_at: Mapped[str] = mapped_column(default=utc_now_text)


class AccessRequest(Base):
    __tablename__ = "access_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    module: Mapped[str]
    note: Mapped[str] = mapped_column(default="")
    status: Mapped[str] = mapped_column(default="pending")  # pending / approved / rejected
    created_at: Mapped[str] = mapped_column(default=utc_now_text)
    decided_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[str] = mapped_column(nullable=True)
    decision_note: Mapped[str] = mapped_column(default="")
