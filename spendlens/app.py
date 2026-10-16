import os
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(__file__))
from database import init_db
from routes.api import router, refresh_and_snapshot
from prices import start_scheduler
from db.migrate import upgrade_head

init_db()
upgrade_head()  # applies Alembic's migrations on top of init_db()'s baseline shape - see db/migrate.py

app = FastAPI(title="SpendLens API")

# No cookie or header-based credential is ever sent (there is no login yet), so
# `allow_credentials=True` next to a wildcard origin would be both meaningless and a
# contradiction browsers reject outright for credentialed requests. Drop it until real
# auth (Phase 4 of ROADMAP.md) needs it, at which point allow_origins must also narrow
# to the actual frontend origin(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
start_scheduler(refresh_and_snapshot)  # daily equity / NAV update after market close, with catch-up

# Built frontend (pnpm --filter @workspace/spendlens run build)
web_dir = Path(__file__).parent.parent / "artifacts" / "spendlens" / "dist" / "public"

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
    uvicorn.run(app, host="0.0.0.0", port=port)
