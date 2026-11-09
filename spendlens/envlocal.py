"""DATABASE_URL (and friends) from the git-ignored .env.local in the project root, unless already set, so app.py and
the command-line tools use PostgreSQL when it is configured. No file: SQLite, exactly as before.
Must run before anything imports db.engine, which reads DATABASE_URL once."""
import os
from pathlib import Path


def load():
    env_file = Path(__file__).resolve().parent.parent / ".env.local"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key in ("DATABASE_URL", "SPENDLENS_MIRROR") and key not in os.environ:
            os.environ[key] = value.strip()
