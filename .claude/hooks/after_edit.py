"""PostToolUse (Edit, Write): lint an edited Python file with ruff (safe fixes applied), and note what the Stop hook
must check before the turn may end. Remaining ruff findings go back to Claude (exit 2) so it fixes them now.

Works for edits inside a git worktree too (a subagent run with worktree isolation): the file's own checkout, not the
session's project directory, decides where ruff and the tests run."""
import subprocess
import sys
from pathlib import Path

from hooklib import git_root, load_state, project_dir, read_input, rel_path, save_state, venv_python

SKIP = ("venv_expense/", "node_modules/", ".claude/")


def main():
    data = read_input()
    file_path = (data.get("tool_input") or {}).get("file_path") or ""
    if not file_path:
        return
    root = git_root(Path(file_path)) or project_dir()
    rel = rel_path(root, file_path)
    if not rel or rel.startswith(SKIP) or "/node_modules/" in rel:
        return
    session = data.get("session_id", "")
    state = load_state(root, session)
    if rel.endswith(".py"):
        absolute = str(Path(file_path).resolve())
        if absolute not in state["py"]:
            state["py"].append(absolute)
        save_state(root, session, state)
        r = subprocess.run([venv_python(root), "-m", "ruff", "check", "--fix", "--quiet", "--output-format", "concise",
                            rel], cwd=root, capture_output=True, text=True, timeout=60)
        if r.returncode == 1:
            print(f"ruff found problems in {rel} (safe fixes were applied):\n{r.stdout.strip()}", file=sys.stderr)
            sys.exit(2)
    elif rel.startswith("artifacts/spendlens/") and rel.endswith((".ts", ".tsx")):
        if str(root) not in state["ts"]:
            state["ts"].append(str(root))
        save_state(root, session, state)


if __name__ == "__main__":
    main()
