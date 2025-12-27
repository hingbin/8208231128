from __future__ import annotations
import json
from typing import Any, Dict
from sqlalchemy import text
from sqlalchemy.engine import Engine
from ..db import get_engine, get_all_db_keys
from ..services.emailer import send_conflict_email
from ..config import settings
from datetime import datetime
from decimal import Decimal

# Tables we sync (must exist in all 3 DBs)
SYNC_TABLES = [
    "users", "customers", "products", "orders", "order_items"
]

# Column lists used to build INSERT/UPDATE statements. Keep in sync with SQL schema.
TABLE_COLUMNS: dict[str, list[str]] = {
    "users": ["user_id","username","password_hash","role","created_at","updated_at","updated_by_db","row_version"],
    "customers": ["customer_id","customer_name","email","phone","created_at","updated_at","updated_by_db","row_version"],
    "products": ["product_id","product_name","price","stock","created_at","updated_at","updated_by_db","row_version"],
    "orders": ["order_id","customer_id","order_date","total_amount","status","created_at","updated_at","updated_by_db","row_version"],
    "order_items": ["item_id","order_id","product_id","quantity","price","created_at","updated_at","updated_by_db","row_version"],
}

TABLE_PK: dict[str, str] = {
    "users": "user_id",
    "customers": "customer_id",
    "products": "product_id",
    "orders": "order_id",
    "order_items": "item_id",
}

def _select_by_pk(conn, table: str, pk: Any):
    pk_col = TABLE_PK[table]
    return conn.execute(text(f"SELECT * FROM {table} WHERE {pk_col}=:pk"), {"pk": pk}).mappings().first()

def _insert_row(conn, table: str, row: Dict[str, Any]):
    cols = TABLE_COLUMNS[table]
    data = {k: row.get(k) for k in cols}
    placeholders = ", ".join([f":{c}" for c in cols])
    col_list = ", ".join(cols)
    conn.execute(text(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"), data)

def _update_row(conn, table: str, row: Dict[str, Any]):
    cols = TABLE_COLUMNS[table]
    pk_col = TABLE_PK[table]
    data = {k: row.get(k) for k in cols}
    sets = ", ".join([f"{c}=:{c}" for c in cols if c != pk_col])
    conn.execute(text(f"UPDATE {table} SET {sets} WHERE {pk_col}=:{pk_col}"), data)

def _record_conflict(control_conn, *, table: str, pk: str, source_db: str, target_db: str, source_row: Dict[str, Any], target_row: Dict[str, Any]) -> int:
    def _json_default(val: Any):
        if isinstance(val, datetime):
            return val.isoformat()
        if isinstance(val, Decimal):
            return float(val)
        return str(val)

    control_conn.execute(text("""
        INSERT INTO conflicts(table_name, pk_value, source_db, target_db, source_row_data, target_row_data, status)
        VALUES (:t, :pk, :sdb, :tdb, :srow, :trow, 'OPEN')
    """), {
        "t": table,
        "pk": pk,
        "sdb": source_db,
        "tdb": target_db,
        "srow": json.dumps(source_row, ensure_ascii=False, default=_json_default),
        "trow": json.dumps(target_row, ensure_ascii=False, default=_json_default),
    })
    rid = control_conn.execute(text("""
        SELECT conflict_id FROM conflicts
        WHERE table_name=:t AND pk_value=:pk AND status='OPEN'
        ORDER BY conflict_id DESC
    """), {"t": table, "pk": pk}).scalar()
    return int(rid)


def _normalize_row_types(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    SQL Server emits datetime values as ISO strings (e.g. 2025-12-19T12:34:56.1234567Z),
    which MySQL won't accept as-is. Also, SQL Server JSON turns BIT into true/false,
    but Postgres schema uses SMALLINT; convert bool -> int. Convert any *_at fields to
    datetime objects so the dialect drivers handle them correctly.
    """
    def _parse_dt(val):
        if isinstance(val, datetime):
            return val
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            except Exception:
                return val
        return val

    for k in list(row.keys()):
        if k.endswith("_at"):
            row[k] = _parse_dt(row[k])
        else:
            v = row[k]
            if isinstance(v, bool):
                row[k] = int(v)
    return row

def apply_change_to_targets(source_db: str, change: dict) -> None:
    table = change["table_name"]
    if table not in SYNC_TABLES:
        return
    pk = change["pk_value"]
    pk_col = TABLE_PK[table]
    op = change["op_type"]
    row = json.loads(change["row_data"]) if isinstance(change["row_data"], str) else change["row_data"]
    row_version_in = int(row.get("row_version") or 1)
    row = _normalize_row_types(row)
    row[pk_col] = row.get(pk_col) or pk

    # Always keep the row stamped as coming from the source DB, so triggers in target won't log it.
    row["updated_by_db"] = source_db.upper()

    targets = [k for k in get_all_db_keys() if k != source_db]
    control_eng = get_engine(settings.control_db)

    for tgt in targets:
        tgt_eng = get_engine(tgt)
        with tgt_eng.begin() as tgt_conn, control_eng.begin() as ctl_conn:
            existing = _select_by_pk(tgt_conn, table, pk)
            if existing is None:
                if op in ("I","U"):
                    _insert_row(tgt_conn, table, row)
                continue

            existing_ver = int(existing.get("row_version") or 1)
            existing_updated_by = (existing.get("updated_by_db") or "").upper()

            if existing_ver > row_version_in and existing_updated_by != source_db.upper():
                cid = _record_conflict(
                    ctl_conn,
                    table=table, pk=pk,
                    source_db=source_db.upper(),
                    target_db=tgt.upper(),
                    source_row=row,
                    target_row=dict(existing),
                )
                try:
                    send_conflict_email(
                        cid,
                        context={
                            "table": table,
                            "pk": str(pk),
                            "source_db": source_db.upper(),
                            "target_db": tgt.upper(),
                        },
                    )
                except Exception:
                    pass
                continue

            if op in ("I","U"):
                _update_row(tgt_conn, table, row)

def mark_processed(eng: Engine, change_id: int) -> None:
    with eng.begin() as conn:
        conn.execute(text("UPDATE change_log SET processed=1, processed_at=CURRENT_TIMESTAMP WHERE change_id=:id"), {"id": change_id})
