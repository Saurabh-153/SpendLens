"""PreToolUse (Bash, PowerShell): refuse shell commands that could lose real data or the user's uncommitted work.

- Migrations (alembic upgrade/downgrade/stamp) run only when the same command points SPENDLENS_DB away from the real
  file or DATABASE_URL at a *_test database: a bare `alembic upgrade` migrates spendlens/spendlens_v2.db.
- Deleting, moving or overwriting the database files, the mirror state, database-mode.json or .env.local is refused,
  and so is printing .env.local (it holds the database passwords).
- Force pushes are refused (--force-with-lease is allowed).
- Commands that throw away uncommitted work (reset --hard, clean, checkout/restore of files, stash drop) ask first.
"""
import json
import re
import sys

from hooklib import read_input

PROTECTED = re.compile(r"spendlens_v2\.db|spendlens_ops\.db|pre-postgres\.bak|\.mirror\.json|\.sync\.json"
                       r"|database-mode\.json|\.env\.local", re.I)
DELETE_OR_MOVE = re.compile(r"^(rm|del|erase|rd|rmdir|ri|mv|move|ren|rename|truncate|Remove-Item|Move-Item"
                            r"|Rename-Item|Clear-Content|Set-Content|Out-File|New-Item)$", re.I)
COPY = re.compile(r"^(cp|copy|Copy-Item|xcopy|robocopy)$", re.I)
READ = re.compile(r"^(cat|type|gc|Get-Content|more|less|head|tail|grep|rg|sed|awk|Select-String|sls|findstr|strings)$",
                  re.I)


def decide(decision, reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                             "permissionDecisionReason": reason}}))
    sys.exit(0)


def segments(cmd):
    return [s.strip() for s in re.split(r"&&|\|\||[;|\n]", cmd) if s.strip()]


def check_migration(cmd):
    if not re.search(r"\balembic\b.*\b(upgrade|downgrade|stamp)\b", cmd):
        return
    db = re.search(r"SPENDLENS_DB['\"]?\s*=\s*['\"]?([^'\";\s]+)", cmd)
    url = re.search(r"DATABASE_URL['\"]?\s*=\s*['\"]?([^'\";\s]+)", cmd)
    if url and url.group(1).rstrip("/").endswith("_test"):
        return
    if db and not url and "spendlens_v2.db" not in db.group(1):
        return
    decide("deny", "This would migrate the real database (spendlens/spendlens_v2.db or DATABASE_URL). Set "
                   "SPENDLENS_DB to a scratch copy, or DATABASE_URL to a *_test database, in the same command. "
                   "Migrating the real database is for the user to run.")


def check_protected_files(cmd):
    for seg in segments(cmd):
        if not PROTECTED.search(seg):
            continue
        words = seg.split()
        verb = words[0].lstrip("&").strip("'\"")
        if READ.match(verb) and ".env.local" in seg.lower():
            decide("deny", ".env.local holds the database passwords; don't print it. Code that needs DATABASE_URL "
                           "reads it itself (app.py, run-api.ps1, conftest with SPENDLENS_TEST_PG=1).")
        redirect = re.search(r">{1,2}\s*['\"]?([^'\"\s]+)", seg)
        if (DELETE_OR_MOVE.match(verb)
                or (COPY.match(verb) and PROTECTED.search(words[-1]))
                or (redirect and PROTECTED.search(redirect.group(1)))):
            decide("deny", "That would delete, move or overwrite a protected file (the databases, their mirror "
                           "state, database-mode.json or .env.local). Work on a copy instead; changes to these "
                           "files are for the user to make.")


def check_git(cmd):
    for seg in segments(cmd):
        if not re.match(r"git\b", seg):
            continue
        if re.search(r"\bpush\b", seg) and re.search(r"\s(--force(?!-with-lease)\b|-f\b|\+\S)", seg):
            decide("deny", "Force pushes are not allowed from an agent. Use --force-with-lease, or ask the user.")
        if (re.search(r"\breset\b.*--hard", seg) or re.search(r"\bclean\b", seg)
                or re.search(r"\bcheckout\b.*\s--\s", seg) or re.search(r"\bcheckout\s+\.\s*$", seg)
                or (re.search(r"\brestore\b", seg) and "--staged" not in seg)
                or re.search(r"\bstash\s+(drop|clear)\b", seg) or re.search(r"\bbranch\s+-D\b", seg)):
            decide("ask", "This can throw away uncommitted work, and the working tree has a lot of it. "
                          "Confirm only if you mean it.")


def main():
    data = read_input()
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if cmd:
        check_migration(cmd)
        check_protected_files(cmd)
        check_git(cmd)


if __name__ == "__main__":
    main()
