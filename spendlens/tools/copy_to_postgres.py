"""Copy every table of a SpendLens SQLite file into a PostgreSQL database, then verify the copy.

    python spendlens/tools/copy_to_postgres.py --source path/to/spendlens_v2.db --target postgresql+psycopg://...

Both databases are first brought to the latest Alembic revision. The target's tables are then emptied
(TRUNCATE ... RESTART IDENTITY) and refilled from the source, so the command can be re-run safely; the
source is only read. Values are coerced to the target column types (SQLite stores 0/1 for booleans and
does not enforce declared types). Finally every table is compared row by row via a checksum.
The copy itself lives in db/replicate.py, which the app's SQLite mirror uses in the other direction.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine  # noqa: E402

from db.replicate import SchemaMismatch, build_schema, copy_all  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", required=True, help="SQLite file to copy from (read only)")
    ap.add_argument("--target", default=os.environ.get("DATABASE_URL"), help="PostgreSQL URL (default: $DATABASE_URL)")
    args = ap.parse_args()
    if not args.target or not args.target.startswith("postgresql"):
        sys.exit("--target must be a postgresql URL")
    source_path = os.path.abspath(args.source)
    source_url = f"sqlite:///{source_path}"

    print("Bringing both databases to the latest schema...")
    build_schema(source_url, source_path)
    build_schema(args.target)

    src, tgt = create_engine(source_url), create_engine(args.target)
    try:
        tables, mismatches = copy_all(src, tgt, log=lambda name, n: print(f"  {name:34} {n:6} rows"))
    except SchemaMismatch as e:
        sys.exit(str(e))
    print("Verifying...")
    for name, a, b in mismatches:
        print(f"  MISMATCH {name}: source {a} rows, target {b} rows")
    if mismatches:
        sys.exit(f"{len(mismatches)} table(s) differ")
    print(f"All {len(tables)} tables match.")


if __name__ == "__main__":
    main()
