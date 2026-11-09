"""Shared by the Claude Code hooks in this folder. Standard library only: the hooks run on whatever `python` is on
PATH, and find the project's venv themselves (a git worktree has no venv_expense/ of its own)."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])


def _git(cwd: Path, *args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def main_checkout(root: Path) -> Path:
    """The primary checkout, which owns venv_expense/ and node_modules/ when `root` is a worktree."""
    out = _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(out).parent if out else root


def git_root(path: Path) -> Path | None:
    """The checkout (main or worktree) that contains `path`."""
    d = path if path.is_dir() else path.parent
    out = _git(d, "rev-parse", "--show-toplevel") if d.exists() else ""
    return Path(out) if out else None


def is_worktree(root: Path) -> bool:
    git_dir = _git(root, "rev-parse", "--path-format=absolute", "--git-dir")
    common = _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return bool(git_dir and common) and Path(git_dir).resolve() != Path(common).resolve()


def ensure_worktree(root: Path) -> list[str]:
    """Make a linked worktree usable: install node_modules from the pnpm store. Python needs nothing, since the hooks
    use the main checkout's venv (`venv_python`). `.env.local` is deliberately not copied: every PostgreSQL test run
    wipes the one shared `_test` database, so parallel worktrees must not run it. Returns what it did."""
    if not is_worktree(root) or (root / "artifacts/spendlens/node_modules").exists():
        return []
    pnpm = shutil.which("pnpm") or "pnpm"
    try:
        r = subprocess.run([pnpm, "install", "--frozen-lockfile", "--prefer-offline"], cwd=root, capture_output=True,
                           text=True, timeout=300)
        return ["pnpm install: " + ("ok" if r.returncode == 0 else f"failed\n{(r.stdout + r.stderr)[-1500:]}")]
    except (OSError, subprocess.SubprocessError) as e:
        return [f"pnpm install failed: {e}"]


def venv_python(root: Path) -> str:
    for base in (root, main_checkout(root)):
        for rel in ("venv_expense/Scripts/python.exe", "venv_expense/bin/python"):
            if (base / rel).exists():
                return str(base / rel)
    return sys.executable


def read_input() -> dict:
    try:
        return json.load(sys.stdin)
    except ValueError:
        return {}


def rel_path(root: Path, file_path: str) -> str | None:
    """`file_path` relative to the project, with forward slashes, or None when it is outside it."""
    try:
        return Path(file_path).resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return None


# What the Stop hook still has to check for a session: edited Python files (absolute paths, since a subagent may edit
# inside a worktree), the checkouts whose TS changed, and failed attempts. Kept in the main checkout's .claude/.state.
def _state_file(root: Path, session_id: str) -> Path:
    return main_checkout(root) / ".claude" / ".state" / f"{session_id or 'default'}.json"


def load_state(root: Path, session_id: str) -> dict:
    try:
        state = json.loads(_state_file(root, session_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    ts = state.get("ts") or []
    return {"py": state.get("py") or [], "ts": ts if isinstance(ts, list) else [], "attempts": state.get("attempts", 0)}


def save_state(root: Path, session_id: str, state: dict):
    f = _state_file(root, session_id)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(state), encoding="utf-8")


def clear_state(root: Path, session_id: str):
    _state_file(root, session_id).unlink(missing_ok=True)
