"""SessionStart / CwdChanged: when Claude is working in a linked git worktree, make it usable (node_modules from the
pnpm store) and tell Claude the rules that differ from the main checkout. Does nothing in the main checkout."""
import json
from pathlib import Path

from hooklib import ensure_worktree, git_root, is_worktree, main_checkout, project_dir, read_input

RULES = """You are in a git worktree ({root}) of SpendLens, not the main checkout ({main}).
- Python: there is no venv_expense/ here. Use "{python}" (the main checkout's venv) for pytest, ruff and alembic.
- PostgreSQL tests: this worktree has no .env.local on purpose. Every PostgreSQL run wipes the one shared _test
  database, so parallel worktrees must not run it; it runs once in the main checkout after merging. SQLite tests are
  safe here (each run gets its own temp database).
- Don't start the app on port 5000 (the main checkout's); set PORT to something else if you must run it. Here it
  would use a fresh, seeded spendlens/spendlens_v2.db of its own, not the user's data.
- Commit your work on this worktree's branch when its tests pass, so it can be merged back."""


def main():
    data = read_input()
    cwd = Path(data.get("cwd") or project_dir())
    root = git_root(cwd)
    if not root or not is_worktree(root):
        return
    done = ensure_worktree(root)
    main_root = main_checkout(root)
    context = RULES.format(root=root, main=main_root, python=main_root / "venv_expense" / "Scripts" / "python.exe")
    if done:
        context += "\nSetup just ran: " + "; ".join(done)
    event = data.get("hook_event_name") or "SessionStart"
    if event == "SessionStart":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}))
    else:
        print(json.dumps({"systemMessage": f"Worktree {root.name}: " + ("; ".join(done) or "ready"),
                          "hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}))


if __name__ == "__main__":
    main()
