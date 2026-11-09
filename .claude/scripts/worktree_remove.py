"""Remove a SpendLens git worktree and, if it has been merged, its branch.

    python .claude/scripts/worktree_remove.py <worktree path> [--force]

On Windows `git worktree remove` fails on pnpm's node_modules (junctions and long paths), so those are deleted
first with shutil.rmtree, which does not follow junctions into the shared pnpm store. Refuses a path that isn't a
linked worktree of this repo, and refuses uncommitted changes unless --force. Deletes the branch only with
`git branch -d`, i.e. only when it is merged.
"""
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
from hooklib import git_root, is_worktree, main_checkout  # noqa: E402


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def main():
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    if len(args) != 1:
        sys.exit(__doc__)
    wt = git_root(Path(args[0]).resolve())
    here = main_checkout(Path(__file__).resolve().parents[2])
    if not wt or not is_worktree(wt) or main_checkout(wt).resolve() != here.resolve():
        sys.exit(f"{args[0]} is not a linked worktree of {here}")
    dirty = [line for line in git(wt, "status", "--porcelain").stdout.splitlines() if line.strip()]
    if dirty and not force:
        sys.exit(f"{wt.name} has uncommitted changes (commit them, or pass --force to discard):\n" + "\n".join(dirty[:20]))
    branch = git(wt, "branch", "--show-current").stdout.strip()

    for nm in (wt / "artifacts/spendlens/node_modules", wt / "node_modules"):
        if nm.exists():
            shutil.rmtree(nm)
    r = git(here, "worktree", "remove", *(["--force"] if force or dirty else []), str(wt))
    if r.returncode != 0 and wt.exists():   # leftovers git couldn't delete: the worktree is already unregistered
        shutil.rmtree(wt)
    git(here, "worktree", "prune")
    print(f"removed worktree {wt}")

    if branch:
        d = git(here, "branch", "-d", branch)
        print(f"deleted branch {branch}" if d.returncode == 0 else f"kept branch {branch}: {d.stderr.strip()}")


if __name__ == "__main__":
    main()
