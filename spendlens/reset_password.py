"""Reset a SpendLens login's password from the command line, for when it is forgotten.

    python spendlens/reset_password.py admin@spendlens.local          # asks for the new password (hidden)
    python spendlens/reset_password.py admin@spendlens.local --random # sets and prints a random one instead

Only someone who can run commands on this computer can do this, so there is no reset on the sign-in page. The user's
existing sign-ins are ended. Stop the backend first (it shares the SQLite mirror); start it again afterwards.
"""
import argparse
import getpass
import os
import secrets
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MIN_LENGTH = 8


def _backend_running(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("email")
    ap.add_argument("--random", action="store_true", help="set a random password and print it")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)))
    args = ap.parse_args(argv)
    if _backend_running(args.port):
        raise SystemExit(f"The backend is running on port {args.port}. Stop it first, then run this again.")

    if args.random or not sys.stdin.isatty():
        password = secrets.token_urlsafe(12)
    else:
        password = getpass.getpass("New password: ")
        if password != getpass.getpass("Again: "):
            raise SystemExit("The two passwords differ; nothing changed.")
        if len(password) < MIN_LENGTH:
            raise SystemExit(f"Use at least {MIN_LENGTH} characters; nothing changed.")

    import envlocal
    envlocal.load()
    import auth
    from db import failover
    from db.engine import SessionLocal
    from db.models import AuthSession, User

    failover.startup()
    try:
        with SessionLocal() as s:
            email = args.email.strip().lower()
            user = s.query(User).filter(User.email == email).first()
            if user is None:
                known = ", ".join(e for (e,) in s.query(User.email).order_by(User.id)) or "none"
                raise SystemExit(f"No login {email}. Logins: {known}")
            user.password_hash = auth.hash_password(password)
            user.is_active = True
            ended = s.query(AuthSession).filter(AuthSession.user_id == user.id).delete(synchronize_session=False)
            s.commit()
        print(f"Password reset for {email} ({user.role}); {ended} old sign-in(s) ended.")
        if args.random or not sys.stdin.isatty():
            print(f"New password: {password}   (sign in, then use Change password at the top right)")
    finally:
        failover.shutdown()


if __name__ == "__main__":
    main()
