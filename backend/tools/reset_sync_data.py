from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Connection

# Ensure `app` package is importable when running the script from repo root.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import get_engine, get_all_db_keys  # noqa: E402

# Child tables must be cleared before their parents when FK constraints exist.
SYNC_TABLES_DELETE_ORDER = ["order_items", "orders", "products", "customers", "users"]
META_TABLES = ["change_log", "conflicts"]
ALL_TARGET_TABLES = SYNC_TABLES_DELETE_ORDER + META_TABLES


def _fetch_counts(conn: Connection, tables: List[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for table in tables:
        res = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
        counts[table] = int(res.scalar() or 0)
    return counts


def _reset_mysql(conn: Connection) -> None:
    conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
    for table in ALL_TARGET_TABLES:
        conn.execute(text(f"TRUNCATE TABLE {table}"))
    conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))


def _reset_postgres(conn: Connection) -> None:
    joined = ", ".join(ALL_TARGET_TABLES)
    conn.execute(text(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE"))


def _reset_mssql(conn: Connection) -> None:
    for table in ALL_TARGET_TABLES:
        conn.execute(text(f"DELETE FROM {table}"))


def clear_database(db_key: str) -> Tuple[Dict[str, int], Dict[str, int]]:
    db_key = db_key.lower()
    eng = get_engine(db_key)
    with eng.begin() as conn:
        before = _fetch_counts(conn, ALL_TARGET_TABLES)
        if db_key == "mysql":
            _reset_mysql(conn)
        elif db_key == "postgres":
            _reset_postgres(conn)
        elif db_key == "mssql":
            _reset_mssql(conn)
        else:
            raise ValueError(f"Unsupported db_key: {db_key}")
        after = _fetch_counts(conn, ALL_TARGET_TABLES)
    return before, after


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clear sync demo tables (users/customers/products/orders/order_items/change_log/conflicts) "
                    "across MySQL, PostgreSQL, and SQL Server."
    )
    parser.add_argument(
        "--db",
        choices=["mysql", "postgres", "mssql", "all"],
        default="all",
        help="Target database to reset (default: all three).",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip interactive confirmation.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    targets = get_all_db_keys() if args.db == "all" else [args.db]

    print("Target databases:", ", ".join(targets))
    print("Tables to clear:", ", ".join(ALL_TARGET_TABLES))
    if not args.yes:
        confirm = input("Type 'yes' to truncate/delete all data listed above: ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            return 1

    failures: Dict[str, str] = {}
    for db_key in targets:
        print(f"\nClearing {db_key} ...")
        try:
            before, after = clear_database(db_key)
        except Exception as exc:
            failures[db_key] = str(exc)
            print(f"  ERROR: {exc}")
            continue

        total_removed = sum(before.values())
        print(f"  Rows removed: {total_removed}")
        for table in ALL_TARGET_TABLES:
            delta = before[table]
            print(f"    {table}: {delta} -> {after[table]}")

    if failures:
        print("\nCompleted with errors:")
        for db_key, err in failures.items():
            print(f"  {db_key}: {err}")
        return 2

    print("\nAll requested databases cleared successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
