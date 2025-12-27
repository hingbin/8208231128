from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth import hash_password
from ..db import get_engine
from ..sync.replicator import TABLE_PK

INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+([a-zA-Z_][\w]*)\s*\(([^)]+)\)\s*VALUES\s*(.*?);",
    re.IGNORECASE | re.DOTALL,
)

TABLE_NAME_MAP: Dict[str, str] = {
    "user": "users",
    "users": "users",
    "customer": "customers",
    "customers": "customers",
    "product": "products",
    "products": "products",
    "order": "orders",
    "orders": "orders",
    "order_item": "order_items",
    "order_items": "order_items",
}

INT_COLUMNS = {"stock", "quantity"}
FLOAT_COLUMNS = {"price", "total_amount"}
PASSWORD_HASH_PREFIXES = ("$2a$", "$2b$", "$2y$", "$2x$", "$bcrypt", "$argon2", "pbkdf2:")


class DatabaseTableImportError(Exception):
    """Raised when the database_table file cannot be parsed or applied."""


def import_database_table_file(db_key: str, file_path: Path) -> Dict[str, int]:
    if not file_path.exists():
        raise FileNotFoundError(f"{file_path} does not exist")

    rows_by_table = _parse_inserts(file_path.read_text(encoding="utf-8"))
    if not rows_by_table:
        raise DatabaseTableImportError("database_table 文件中没有可用的 INSERT 语句")

    db_key = db_key.lower()
    eng = get_engine(db_key)
    dbtag = db_key.upper()
    inserted: Dict[str, int] = {table: 0 for table in rows_by_table}

    with eng.begin() as conn:
        for table, rows in rows_by_table.items():
            pk_col = TABLE_PK.get(table)
            if not pk_col:
                continue
            for row in rows:
                payload = _build_payload(table, row, dbtag, pk_col)
                if table == "users" and _user_exists(conn, payload.get("username")):
                    continue
                exists = conn.execute(
                    text(f"SELECT 1 FROM {table} WHERE {pk_col}=:pk"),
                    {"pk": payload[pk_col]},
                ).first()
                if exists:
                    continue
                columns = ", ".join(payload.keys())
                placeholders = ", ".join(f":{c}" for c in payload.keys())
                conn.execute(
                    text(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"),
                    payload,
                )
                inserted[table] += 1

    return inserted


def _parse_inserts(sql: str) -> Dict[str, List[Dict[str, Any]]]:
    rows_by_table: Dict[str, List[Dict[str, Any]]] = {}
    for match in INSERT_RE.finditer(sql):
        raw_table = match.group(1).strip().lower()
        table = TABLE_NAME_MAP.get(raw_table)
        if not table:
            continue
        columns = [col.strip() for col in match.group(2).split(",") if col.strip()]
        values_block = _clean_values(match.group(3))
        if not values_block:
            continue
        try:
            parsed_rows = ast.literal_eval(f"[{values_block}]")
        except (SyntaxError, ValueError) as exc:
            raise DatabaseTableImportError(
                f"无法解析 {match.group(1)} 的 INSERT 语句：{exc}"
            ) from exc
        if not isinstance(parsed_rows, list):
            raise DatabaseTableImportError(f"{match.group(1)} 的数据格式不正确")

        table_rows = rows_by_table.setdefault(table, [])
        for row in parsed_rows:
            if not isinstance(row, (tuple, list)):
                raise DatabaseTableImportError(f"{match.group(1)} 的某一行格式不正确")
            if len(row) != len(columns):
                raise DatabaseTableImportError(
                    f"{match.group(1)} 的列数与数据不匹配"
                )
            record = {columns[i]: row[i] for i in range(len(columns))}
            table_rows.append(record)

    return rows_by_table


def _clean_values(block: str) -> str:
    cleaned_parts: List[str] = []
    for raw in block.splitlines():
        line = raw.split("--", 1)[0].strip()
        if line:
            cleaned_parts.append(line)
    cleaned = " ".join(cleaned_parts).rstrip(",")
    return cleaned


def _build_payload(table: str, row: Dict[str, Any], dbtag: str, pk_col: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    for col, value in row.items():
        payload[col] = _convert_value(col, value)

    if pk_col not in payload:
        raise DatabaseTableImportError(f"{table} 缺少主键列 {pk_col}")
    payload[pk_col] = _ensure_str(payload[pk_col])
    payload.setdefault("updated_by_db", dbtag)
    payload.setdefault("row_version", 1)

    if table == "users":
        payload["password_hash"] = _normalize_password_hash(payload.get("password_hash"))

    return payload


def _convert_value(column: str, value: Any) -> Any:
    if value is None:
        return None
    column_lower = column.lower()
    if column_lower.endswith("_id"):
        return _ensure_str(value)
    if column_lower in INT_COLUMNS:
        return int(value)
    if column_lower in FLOAT_COLUMNS:
        return float(value)
    return value


def _ensure_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def _normalize_password_hash(value: Any) -> str:
    raw = (value or "").strip()
    if any(raw.startswith(prefix) for prefix in PASSWORD_HASH_PREFIXES):
        return raw
    if not raw:
        raw = "changeme123"
    return hash_password(raw)


def _user_exists(conn: Connection, username: Any) -> bool:
    if not username:
        raise DatabaseTableImportError("users 数据缺少 username")
    row = conn.execute(
        text("SELECT 1 FROM users WHERE username=:u"),
        {"u": str(username)},
    ).first()
    return row is not None
