"""Stop: before Claude ends a turn that edited code, run the typecheck (if TS changed) and the tests nearest the
edited Python files. A failure blocks the stop and hands Claude the output, at most MAX_ATTEMPTS times in a row; after
that it stops anyway and tells the user. The full suite (~100 s) and `pnpm run check` stay manual / CI."""
import json
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

from hooklib import (clear_state, ensure_worktree, git_root, load_state, project_dir, read_input, rel_path, save_state,
                     venv_python)

MAX_ATTEMPTS = 3

# Backend module stem -> tests that cover it, where `tests/test_<stem>*.py` doesn't find them.
ALIASES = {
    "auth": ["test_access.py", "test_isolation.py"],
    "app": ["test_api_shape.py"],
    "investing": ["test_portfolio_sqla.py", "test_mix_math.py"],
    "portfolio": ["test_portfolio_sqla.py", "test_mix_math.py"],
    "sip": ["test_portfolio_sqla.py"], "accrual": ["test_portfolio_sqla.py"],
    "ledger": ["test_portfolio_sqla.py"], "prices": ["test_portfolio_sqla.py"],
    "status": ["test_mirror_failover.py"],
    "database": ["test_migrations.py", "test_core_sqla.py"],
    "subcategories": ["test_expense_writes.py", "test_core_sqla.py"],
    "expense": ["test_expense_writes.py", "test_category_delete.py"],
}
DB_TESTS = ["test_migrations.py", "test_core_sqla.py", "test_isolation.py"]
FAILOVER = ("mirror", "failover", "replicate", "engine")


def tests_for(root, paths):
    tests_dir = root / "tests"
    found = set()

    def by_stem(stem):
        hits = [p.name for p in tests_dir.glob(f"test_{stem}*.py")] + ALIASES.get(stem, [])
        found.update(hits)
        return bool(hits)

    for rel in paths:
        name = rel.rsplit("/", 1)[-1]
        stem = name[:-3]
        if rel.startswith("tests/"):
            found.update([name] if name.startswith("test_") else ["test_api_shape.py", "test_isolation.py"])
        elif rel.startswith(("alembic/", "spendlens/db/")):
            found.update(DB_TESTS + (["test_mirror_failover.py"] if stem in FAILOVER else []))
        elif rel.startswith("spendlens/routes/"):
            found.update(["test_api_shape.py", "test_isolation.py"])
            by_stem(stem.removesuffix("_routes"))
        elif rel.startswith("spendlens/"):
            if not by_stem(stem):
                found.add("test_api_shape.py")
    return sorted(t for t in found if (tests_dir / t).exists())


def run(cmd, root, timeout):
    try:
        r = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s: {' '.join(cmd)}"


def main():
    data = read_input()
    root, session = project_dir(), data.get("session_id", "")
    state = load_state(root, session)
    if not state["py"] and not state["ts"]:
        return

    # Edits are grouped by the checkout they were made in: the main one, or a worktree a subagent worked in.
    py_by_root = defaultdict(list)
    for path in state["py"]:
        checkout = git_root(Path(path))
        rel = rel_path(checkout, path) if checkout else None
        if rel:
            py_by_root[checkout].append(rel)

    failures, ran = [], []
    for checkout in sorted({Path(r) for r in state["ts"]} | set(py_by_root)):
        if not checkout.exists():
            continue                      # a worktree that has since been removed
        where = "" if checkout.resolve() == root.resolve() else f" in {checkout.name}"
        ensure_worktree(checkout)
        if str(checkout) in state["ts"]:
            pnpm = shutil.which("pnpm") or "pnpm"
            ok, out = run([pnpm, "run", "typecheck"], checkout, 180)
            ran.append(f"typecheck{where}")
            if not ok:
                failures.append(f"pnpm run typecheck{where} failed:\n{out[-4000:]}")
        tests = tests_for(checkout, py_by_root.get(checkout, []))
        if tests:
            ok, out = run([venv_python(checkout), "-m", "pytest", "-q", "-x", *[f"tests/{t}" for t in tests]],
                          checkout, 480)
            ran.append(f"pytest{where} {' '.join(tests)}")
            if not ok:
                failures.append(f"pytest{where} failed ({' '.join(tests)}):\n{out[-4000:]}")

    if not failures:
        clear_state(root, session)
        print(json.dumps({"systemMessage": "Checks passed: " + "; ".join(ran)}))
        return
    state["attempts"] = state.get("attempts", 0) + 1
    if state["attempts"] > MAX_ATTEMPTS:
        clear_state(root, session)
        print(json.dumps({"systemMessage": f"Checks still failing after {MAX_ATTEMPTS} attempts; stopping anyway. "
                                           "Run them yourself: " + "; ".join(ran)}))
        return
    save_state(root, session, state)
    print(json.dumps({"decision": "block", "reason": "Fix these before finishing (attempt "
                      f"{state['attempts']} of {MAX_ATTEMPTS}):\n\n" + "\n\n".join(failures)}))


if __name__ == "__main__":
    main()
