import os
import sys
from pathlib import Path


import envlocal  # noqa: E402

envlocal.load()  # before anything imports db.engine, which reads DATABASE_URL once
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(__file__))
from routes.api import router, refresh_and_snapshot
from prices import start_scheduler
from db import failover

import auth
import security
failover.startup()  # Alembic builds or upgrades the schema (db/migrate.py); on PostgreSQL also the SQLite mirror
auth.bootstrap_admin()  # first start only: the admin who owns the existing data
auth.announce_reset_code()  # the sign-in page's "Forgot password?" asks for it; only this console shows it

# Only this computer by default. SPENDLENS_HOST=0.0.0.0 opens it to the network (then put HTTPS in front: README).
HOST = os.environ.get("SPENDLENS_HOST", "127.0.0.1")
LOOPBACK = HOST in ("127.0.0.1", "localhost", "::1")
# Swagger / ReDoc / the OpenAPI schema: on for a local-only server, off on the network unless SPENDLENS_DOCS=1.
DOCS = os.environ.get("SPENDLENS_DOCS", "1" if LOOPBACK else "0") == "1"

app = FastAPI(title="SpendLens API", docs_url="/docs" if DOCS else None, redoc_url="/redoc" if DOCS else None,
              openapi_url="/openapi.json" if DOCS else None)

# The login is an HttpOnly cookie, so browsers only accept cross-origin calls from a named origin (never "*").
# The built app and the Vite dev proxy are same-origin and need none of this; set SPENDLENS_CORS_ORIGINS
# (comma-separated) to allow a frontend served from somewhere else.
ORIGINS = [o.strip() for o in os.environ.get("SPENDLENS_CORS_ORIGINS", "http://localhost:5000,http://localhost:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

failover.install(app)  # read-only guard while PostgreSQL is down; see db/failover.py
app.include_router(router)
start_scheduler(refresh_and_snapshot)  # daily equity / NAV update after market close, with catch-up

# Built frontend (pnpm --filter @workspace/spendlens run build)
web_dir = Path(__file__).parent.parent / "artifacts" / "spendlens" / "dist" / "public"
# cross-site request check + security headers (CSP hashes the built index.html's inline script); see security.py
security.install(app, ORIGINS, web_dir / "index.html")

if web_dir.exists():
    app.mount("/assets", StaticFiles(directory=web_dir / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        file = (web_dir / path).resolve()
        if path and file.is_file() and web_dir.resolve() in file.parents:
            return FileResponse(file)
        return FileResponse(web_dir / "index.html")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(app, host=HOST, port=port)
