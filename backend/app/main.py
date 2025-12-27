from __future__ import annotations
import json
import textwrap
import uuid
import sys
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, Literal
from fastapi import FastAPI, Depends, HTTPException, Query, Request, Body
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

# Path bootstrap so importing app.main works
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(PROJECT_ROOT))
elif str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.db import get_engine, get_control_engine, get_all_db_keys
from app.schemas import LoginIn, RegisterIn, TokenOut, ProductIn, DBKey, SQLQueryIn
from app.auth import (
    verify_password, create_access_token, ensure_admin_seeded,
    get_current_user, require_admin, hash_password
)
from app.services.emailer import verify_conflict_token, send_conflict_resolved_email
from app.services.database_table_loader import (
    import_database_table_file,
    DatabaseTableImportError,
)
from app.sync.replicator import (
    SYNC_TABLES,
    TABLE_COLUMNS,
    TABLE_PK,
    _insert_row,
    _update_row,
    _normalize_row_types,
)

app = FastAPI(title="Multi-DB Sync Platform (Scaffold)")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

DBOrAll = Literal["mysql", "postgres", "mssql", "all"]

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

@app.on_event("startup")
def _startup():
    ensure_admin_seeded()

# ---------------- Auth ----------------
@app.post("/auth/login", response_model=TokenOut)
def login(payload: LoginIn):
    eng = get_control_engine()
    with eng.begin() as conn:
        row = conn.execute(
            text("SELECT username, password_hash, role FROM users WHERE username=:u"),
            {"u": payload.username},
        ).mappings().first()
    if not row or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Bad credentials")

    is_admin = (row.get("role") or "").lower() == "admin"
    token = create_access_token(sub=row["username"], is_admin=is_admin)
    return {"access_token": token}

@app.post("/auth/register", response_model=TokenOut)
def register(payload: RegisterIn):
    if payload.registration_code != settings.admin_registration_code:
        raise HTTPException(status_code=400, detail="注册码不正确")

    eng = get_control_engine()
    dbtag = settings.control_db.upper()
    with eng.begin() as conn:
        existing = conn.execute(
            text("SELECT 1 FROM users WHERE username=:u"),
            {"u": payload.username},
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="用户名已存在")

        user_id = str(uuid.uuid4())
        conn.execute(text("""
            INSERT INTO users(user_id, username, password_hash, role, updated_by_db, row_version)
            VALUES (:id, :u, :ph, 'admin', :udb, 1)
        """), {"id": user_id, "u": payload.username, "ph": hash_password(payload.password), "udb": dbtag})

    token = create_access_token(sub=payload.username, is_admin=True)
    return {"access_token": token}

@app.get("/me")
def me(user=Depends(get_current_user)):
    return user

# ---------------- Demo seeding ----------------
@app.post("/demo/seed")
def seed(db: DBKey = Query(..., description="mysql|postgres|mssql")):
    eng = get_engine(db)
    dbtag = db.upper()
    now = datetime.now(timezone.utc)
    customers = [
        {
            "customer_id": "00000000-0000-0000-0000-00000000C001",
            "customer_name": "Acme Corp",
            "email": "ops@acme.example",
            "phone": "13800000001",
        },
        {
            "customer_id": "00000000-0000-0000-0000-00000000C002",
            "customer_name": "Star Retail",
            "email": "hello@starretail.example",
            "phone": "13800000002",
        },
    ]
    products = [
        {
            "product_id": "00000000-0000-0000-0000-00000000P101",
            "product_name": "Data Sync Gateway",
            "price": 1999.00,
            "stock": 25,
        },
        {
            "product_id": "00000000-0000-0000-0000-00000000P102",
            "product_name": "Cross-DB Monitor",
            "price": 2999.00,
            "stock": 18,
        },
        {
            "product_id": "00000000-0000-0000-0000-00000000P103",
            "product_name": "Conflict Inspector",
            "price": 1299.00,
            "stock": 35,
        },
    ]
    orders = [
        {
            "order_id": "00000000-0000-0000-0000-00000000O201",
            "customer_id": customers[0]["customer_id"],
            "order_date": now - timedelta(days=3),
            "status": "PAID",
        },
        {
            "order_id": "00000000-0000-0000-0000-00000000O202",
            "customer_id": customers[1]["customer_id"],
            "order_date": now - timedelta(days=1),
            "status": "CREATED",
        },
    ]
    order_items = [
        {
            "item_id": "00000000-0000-0000-0000-00000000I301",
            "order_id": orders[0]["order_id"],
            "product_id": products[0]["product_id"],
            "quantity": 2,
            "price": 1999.00,
        },
        {
            "item_id": "00000000-0000-0000-0000-00000000I302",
            "order_id": orders[0]["order_id"],
            "product_id": products[2]["product_id"],
            "quantity": 1,
            "price": 1299.00,
        },
        {
            "item_id": "00000000-0000-0000-0000-00000000I303",
            "order_id": orders[1]["order_id"],
            "product_id": products[1]["product_id"],
            "quantity": 1,
            "price": 2999.00,
        },
    ]

    totals: Dict[str, Decimal] = {}
    for item in order_items:
        subtotal = Decimal(str(item["price"])) * Decimal(item["quantity"])
        totals[item["order_id"]] = totals.get(item["order_id"], Decimal("0")) + subtotal
    for order in orders:
        order["total_amount"] = float(totals.get(order["order_id"], Decimal("0")))

    def _ensure(conn, table: str, pk: str, payload: dict):
        data = dict(payload)
        data.setdefault("updated_by_db", dbtag)
        data.setdefault("row_version", 1)
        exists = conn.execute(
            text(f"SELECT 1 FROM {table} WHERE {pk}=:pk"),
            {"pk": data[pk]}
        ).first()
        if exists:
            return
        cols = ", ".join(data.keys())
        vals = ", ".join(f":{k}" for k in data.keys())
        conn.execute(text(f"INSERT INTO {table} ({cols}) VALUES ({vals})"), data)

    with eng.begin() as conn:
        for cust in customers:
            _ensure(conn, "customers", "customer_id", cust)
        for prod in products:
            _ensure(conn, "products", "product_id", prod)
        for order in orders:
            _ensure(conn, "orders", "order_id", order)
        for item in order_items:
            _ensure(conn, "order_items", "item_id", item)

    return {"ok": True, "seeded_db": db, "rows": {
        "customers": len(customers),
        "products": len(products),
        "orders": len(orders),
        "order_items": len(order_items),
    }}

@app.post("/demo/import-database-table")
def import_database_table(db: DBOrAll = Query("all", description="mysql|postgres|mssql|all")):
    data_path = PROJECT_ROOT / "database_table"
    if not data_path.exists():
        raise HTTPException(status_code=404, detail="database_table 文件不存在")

    targets = get_all_db_keys() if db == "all" else [db]
    results: Dict[str, Dict[str, int]] = {}
    total = 0

    for target in targets:
        try:
            counts = import_database_table_file(target, data_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="database_table 文件不存在")
        except DatabaseTableImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        results[target] = counts
        total += sum(counts.values())

    return {
        "ok": True,
        "source": str(data_path),
        "dbs": targets,
        "inserted": results,
        "total_inserted": total,
    }


# ---------------- Manual migration (table/db) ----------------
@app.post("/sync/migrate/table")
def migrate_table(
    source_db: DBKey = Query(..., description="Source DB to copy from"),
    table_name: str = Query(..., description="One of sync tables"),
    target: DBOrAll = Query("all", description="mysql|postgres|mssql|all (all means other DBs)"),
    user=Depends(require_admin),
):
    table = (table_name or "").strip()
    if table not in SYNC_TABLES:
        raise HTTPException(status_code=400, detail=f"不支持的表: {table}")

    source_db = source_db.lower()
    if source_db not in get_all_db_keys():
        raise HTTPException(status_code=400, detail="不支持的来源库")

    targets = [k for k in get_all_db_keys() if k != source_db] if target == "all" else [target]
    targets = [t for t in targets if t != source_db]
    if not targets:
        return {"ok": True, "table": table, "source_db": source_db, "targets": [], "migrated": 0}

    pk_col = TABLE_PK.get(table)
    if not pk_col:
        raise HTTPException(status_code=400, detail="缺少主键信息")

    src_eng = get_engine(source_db)
    with src_eng.begin() as src_conn:
        rows = src_conn.execute(text(f"SELECT * FROM {table}")).mappings().all()

    migrated = 0
    for tgt in targets:
        tgt_eng = get_engine(tgt)
        with tgt_eng.begin() as tgt_conn:
            for row in rows:
                payload = dict(row)
                payload[pk_col] = payload.get(pk_col)
                payload["updated_by_db"] = source_db.upper()
                payload = _normalize_row_types(payload)

                exists = tgt_conn.execute(
                    text(f"SELECT 1 FROM {table} WHERE {pk_col}=:pk"),
                    {"pk": payload[pk_col]},
                ).first()
                if exists is None:
                    _insert_row(tgt_conn, table, payload)
                else:
                    _update_row(tgt_conn, table, payload)
                migrated += 1

    return {"ok": True, "table": table, "source_db": source_db, "targets": targets, "migrated": migrated}


@app.post("/sync/migrate/database")
def migrate_database(
    source_db: DBKey = Query(..., description="Source DB to copy from"),
    target: DBOrAll = Query("all", description="mysql|postgres|mssql|all (all means other DBs)"),
    user=Depends(require_admin),
):
    # Follow FK order: customers/products first, then orders, then order_items.
    ordered_tables = ["users", "customers", "products", "orders", "order_items"]
    results = {}
    total = 0
    for table in ordered_tables:
        res = migrate_table(source_db=source_db, table_name=table, target=target, user=user)
        results[table] = res.get("migrated", 0)
        total += int(res.get("migrated", 0))
    return {"ok": True, "source_db": source_db, "target": target, "tables": results, "total_rows_applied": total}

# ---------------- Products API (writes go to chosen DB) ----------------
@app.get("/products")
def list_products(db: DBKey = Query(...)):
    eng = get_engine(db)
    with eng.begin() as conn:
        rows = conn.execute(text("""
            SELECT product_id, product_name, price, stock, updated_at, updated_by_db, row_version
            FROM products
            ORDER BY updated_at DESC
        """)).mappings().all()
    return list(rows)

@app.post("/products")
def upsert_product(p: ProductIn, db: DBKey = Query(...), user=Depends(get_current_user)):
    eng = get_engine(db)
    dbtag = db.upper()
    pid = p.product_id or str(uuid.uuid4())
    payload = {
        "product_id": pid,
        "product_name": p.product_name,
        "price": float(p.price),
        "stock": int(p.stock),
        "udb": dbtag,
    }
    with eng.begin() as conn:
        existing = conn.execute(text("SELECT 1 FROM products WHERE product_id=:id"), {"id": pid}).first()
        if existing is None:
            conn.execute(text("""
                INSERT INTO products(product_id, product_name, price, stock, updated_by_db, row_version)
                VALUES (:product_id, :product_name, :price, :stock, :udb, 1)
            """), payload)
        else:
            conn.execute(text("""
                UPDATE products
                SET product_name=:product_name, price=:price, stock=:stock, updated_by_db=:udb
                WHERE product_id=:product_id
            """), payload)
    return {"ok": True, "product_id": pid, "id": pid, "written_db": db}

# ---------------- Conflicts API (reads from CONTROL_DB) ----------------
@app.get("/conflicts")
def list_conflicts(status: str = "OPEN", user=Depends(require_admin)):
    eng = get_control_engine()
    with eng.begin() as conn:
        rows = conn.execute(text("""
            SELECT conflict_id, table_name, pk_value, source_db, target_db, status, created_at
            FROM conflicts
            WHERE status=:st
            ORDER BY conflict_id DESC
        """), {"st": status}).mappings().all()
    return list(rows)

@app.get("/conflicts/{conflict_id}")
def conflict_detail(conflict_id: int, user=Depends(require_admin)):
    eng = get_control_engine()
    with eng.begin() as conn:
        row = conn.execute(text("""
            SELECT * FROM conflicts WHERE conflict_id=:id
        """), {"id": conflict_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Not found")
    row = dict(row)
    row["source_row_data"] = json.loads(row["source_row_data"])
    row["target_row_data"] = json.loads(row["target_row_data"])
    return row


@app.get("/conflicts/{conflict_id}/public")
def conflict_detail_public(conflict_id: int, t: str = Query(..., description="token from email link")):
    # Read-only endpoint for token-based access (mobile/PC via email link).
    try:
        payload = verify_conflict_token(t)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    if int(payload.get("conflict_id") or 0) != int(conflict_id):
        raise HTTPException(status_code=403, detail="Token not allowed for this conflict")

    eng = get_control_engine()
    with eng.begin() as conn:
        row = conn.execute(text("SELECT * FROM conflicts WHERE conflict_id=:id"), {"id": conflict_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Not found")
    row = dict(row)
    row["source_row_data"] = json.loads(row["source_row_data"])
    row["target_row_data"] = json.loads(row["target_row_data"])
    return row

@app.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(conflict_id: int, winner_db: DBKey = Query(...), user=Depends(require_admin)):
    eng = get_control_engine()
    with eng.begin() as conn:
        row = conn.execute(text("SELECT * FROM conflicts WHERE conflict_id=:id"), {"id": conflict_id}).mappings().first()
        if not row:
            raise HTTPException(404, "Not found")
        if row["status"] != "OPEN":
            raise HTTPException(400, "Already resolved")

        source_row = json.loads(row["source_row_data"])
        target_row = json.loads(row["target_row_data"])
        chosen = source_row if winner_db.upper() == row["source_db"].upper() else target_row

        # apply chosen row to all DBs (force updated_by_db to winner_db so triggers won't create loops)
        pk_col = TABLE_PK.get(row["table_name"])
        if not pk_col:
            raise HTTPException(400, "不支持的同步表")
        applied_row = dict(chosen)
        pk_value = row["pk_value"]
        applied_row[pk_col] = applied_row.get(pk_col) or pk_value
        applied_row = _normalize_row_types(applied_row)

        for dbk in get_all_db_keys():
            eng_t = get_engine(dbk)
            with eng_t.begin() as c2:
                exists = c2.execute(
                    text(f"SELECT 1 FROM {row['table_name']} WHERE {pk_col}=:pk"),
                    {"pk": pk_value}
                ).first()
                payload = dict(applied_row)
                payload["updated_by_db"] = winner_db.upper()
                payload[pk_col] = pk_value
                if exists is None:
                    _insert_row(c2, row["table_name"], payload)
                else:
                    _update_row(c2, row["table_name"], payload)

        conn.execute(text("""
            UPDATE conflicts
            SET status='RESOLVED', winner_db=:w, resolved_by=:rb, resolved_at=CURRENT_TIMESTAMP
            WHERE conflict_id=:id
        """), {"w": winner_db.upper(), "rb": user["sub"], "id": conflict_id})

    try:
        send_conflict_resolved_email(conflict_id, winner_db.upper())
    except Exception:
        pass

    return {"ok": True, "resolved": conflict_id, "winner_db": winner_db, "applied_row": applied_row}

@app.post("/conflicts/{conflict_id}/resolve/custom")
def resolve_conflict_custom(conflict_id: int, row_override: Dict[str, Any] = Body(...), user=Depends(require_admin)):
    if not isinstance(row_override, dict):
        raise HTTPException(400, "缺少自定义数据")

    eng = get_control_engine()
    with eng.begin() as conn:
        row = conn.execute(text("SELECT * FROM conflicts WHERE conflict_id=:id"), {"id": conflict_id}).mappings().first()
        if not row:
            raise HTTPException(404, "Not found")
        if row["status"] != "OPEN":
            raise HTTPException(400, "Already resolved")

        table = row["table_name"]
        columns = TABLE_COLUMNS.get(table)
        if not columns:
            raise HTTPException(400, "不支持的表")
        pk_col = TABLE_PK.get(table)
        if not pk_col:
            raise HTTPException(400, "缺少主键信息")

        base_row = json.loads(row["source_row_data"])
        payload = {col: base_row.get(col) for col in columns}
        for key, value in row_override.items():
            if key in columns and value is not None:
                payload[key] = value

        payload[pk_col] = payload.get(pk_col) or row["pk_value"]
        if not payload[pk_col]:
            raise HTTPException(400, "缺少主键 ID")
        payload["updated_by_db"] = (user.get("sub") or "CUSTOM").upper()[:16]
        payload["row_version"] = int(payload.get("row_version") or 1)
        payload = _normalize_row_types(payload)

        for dbk in get_all_db_keys():
            eng_t = get_engine(dbk)
            with eng_t.begin() as c2:
                exists = c2.execute(
                    text(f"SELECT 1 FROM {table} WHERE {pk_col}=:pk"),
                    {"pk": payload[pk_col]}
                ).first()
                if exists is None:
                    _insert_row(c2, table, payload)
                else:
                    _update_row(c2, table, payload)

        conn.execute(text("""
            UPDATE conflicts
            SET status='RESOLVED', winner_db='CUSTOM', resolved_by=:rb, resolved_at=CURRENT_TIMESTAMP
            WHERE conflict_id=:id
        """), {"rb": user["sub"], "id": conflict_id})

    try:
        send_conflict_resolved_email(conflict_id, "CUSTOM")
    except Exception:
        pass

    return {"ok": True, "resolved": conflict_id, "winner_db": "custom", "applied_row": payload}

# ---------------- Daily report API (mobile) ----------------
@app.get("/report/daily")
def daily_report(days: int = 7, user=Depends(get_current_user)):
    eng = get_control_engine()
    with eng.begin() as conn:
        # Simple aggregation: processed changes per day + conflicts per day
        changes = conn.execute(text("""
            SELECT CAST(processed_at AS DATE) AS d, COUNT(*) AS changes
            FROM change_log
            WHERE processed=1 AND processed_at IS NOT NULL
            GROUP BY CAST(processed_at AS DATE)
            ORDER BY d DESC
        """)).mappings().all()

        conflicts = conn.execute(text("""
            SELECT CAST(created_at AS DATE) AS d, COUNT(*) AS conflicts
            FROM conflicts
            GROUP BY CAST(created_at AS DATE)
            ORDER BY d DESC
        """)).mappings().all()
        table_rows = conn.execute(text("""
            SELECT CAST(processed_at AS DATE) AS d, table_name, COUNT(*) AS changes
            FROM change_log
            WHERE processed=1 AND processed_at IS NOT NULL
            GROUP BY CAST(processed_at AS DATE), table_name
            ORDER BY d DESC, table_name
        """)).mappings().all()

    changes = list(changes)[:days]
    conflicts = list(conflicts)[:days]

    # Build per-table trend (last N days) so UI can plot each synced table separately.
    table_dates_desc: list[str] = []
    seen_dates: set[str] = set()
    table_entries: list[dict[str, Any]] = []
    for row in table_rows:
        d_val = row["d"]
        d_str = d_val.isoformat() if hasattr(d_val, "isoformat") else str(d_val)
        if d_str not in seen_dates:
            if len(table_dates_desc) >= days:
                break
            table_dates_desc.append(d_str)
            seen_dates.add(d_str)
        table_entries.append({
            "d": d_str,
            "table_name": row["table_name"],
            "changes": int(row["changes"] or 0),
        })

    table_dates = list(reversed(table_dates_desc))
    date_index = {d: idx for idx, d in enumerate(table_dates)}
    table_series: dict[str, list[int]] = {}
    for entry in table_entries:
        idx = date_index.get(entry["d"])
        if idx is None:
            continue
        table_key = entry["table_name"]
        arr = table_series.setdefault(table_key, [0] * len(table_dates))
        arr[idx] = entry["changes"]

    for table in SYNC_TABLES:
        table_series.setdefault(table, [0] * len(table_dates))

    table_trends = {"dates": table_dates, "series": table_series}
    table_volume = _collect_table_volume_totals()

    return {
        "changes": changes,
        "conflicts": conflicts,
        "table_trends": table_trends,
        "table_volume": table_volume,
    }

def _fetch_table_counts(db_key: str) -> dict[str, Any]:
    eng = get_engine(db_key)
    try:
        with eng.begin() as conn:
            row = conn.execute(text("""
                SELECT
                    (SELECT COUNT(*) FROM users) AS users,
                    (SELECT COUNT(*) FROM customers) AS customers,
                    (SELECT COUNT(*) FROM products) AS products,
                    (SELECT COUNT(*) FROM orders) AS orders,
                    (SELECT COUNT(*) FROM order_items) AS order_items,
                    (SELECT COUNT(*) FROM change_log) AS change_log_total,
                    (SELECT COUNT(*) FROM change_log WHERE processed=0) AS pending_changes,
                    (SELECT MAX(updated_at) FROM products) AS last_product_update
            """)).mappings().first()
    except Exception:
        return {
            "users": 0,
            "customers": 0,
            "products": 0,
            "orders": 0,
            "order_items": 0,
            "change_log_total": 0,
            "pending_changes": 0,
            "last_product_update": None,
        }

    return {
        "users": int(row["users"] or 0),
        "customers": int(row["customers"] or 0),
        "products": int(row["products"] or 0),
        "orders": int(row["orders"] or 0),
        "order_items": int(row["order_items"] or 0),
        "change_log_total": int(row["change_log_total"] or 0),
        "pending_changes": int(row["pending_changes"] or 0),
        "last_product_update": row["last_product_update"].isoformat() if row.get("last_product_update") else None,
    }

def _collect_table_volume_totals() -> dict[str, int]:
    """
    Count current row volume for the 7 key tables (users/customers/products/orders/order_items/change_log/conflicts)
    directly from the control database so the UI can always render a bar chart even if other DBs are offline.
    """
    tables = list(SYNC_TABLES) + ["change_log", "conflicts"]
    totals: dict[str, int] = {table: 0 for table in tables}
    try:
        eng = get_control_engine()
        with eng.begin() as conn:
            for table in tables:
                try:
                    totals[table] = int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)
                except Exception:
                    totals[table] = 0
    except Exception:
        pass
    return totals

def _collect_product_matrix(limit: int = 8) -> list[dict[str, Any]]:
    combined: Dict[str, Dict[str, Any]] = {}
    for db_key in get_all_db_keys():
        eng = get_engine(db_key)
        try:
            with eng.begin() as conn:
                if db_key == "mssql":
                    sql = f"""
                        SELECT TOP ({int(limit)}) product_id, product_name, price, stock, updated_at, updated_by_db, row_version
                        FROM products
                        ORDER BY updated_at DESC
                    """
                    rows = conn.execute(text(sql)).mappings().all()
                else:
                    rows = conn.execute(text("""
                        SELECT product_id, product_name, price, stock, updated_at, updated_by_db, row_version
                        FROM products
                        ORDER BY updated_at DESC
                        LIMIT :lim
                    """), {"lim": limit}).mappings().all()
        except Exception:
            rows = []

        for row in rows:
            entry = combined.setdefault(row["product_id"], {
                "product_id": row["product_id"],
                "product_name": row["product_name"],
                "per_db": {},
            })
            entry["per_db"][db_key] = {
                "price": float(row["price"]) if row["price"] is not None else None,
                "stock": int(row["stock"]) if row["stock"] is not None else None,
                "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
                "row_version": int(row.get("row_version") or 1),
                "updated_by_db": row.get("updated_by_db"),
            }

    entries = []
    for entry in combined.values():
        prices = {details["price"] for details in entry["per_db"].values() if details["price"] is not None}
        stocks = {details["stock"] for details in entry["per_db"].values() if details["stock"] is not None}
        entry["has_diff"] = (
            len(prices) > 1
            or len(stocks) > 1
            or len(entry["per_db"]) != len(get_all_db_keys())
        )
        entry["missing_dbs"] = [db for db in get_all_db_keys() if db not in entry["per_db"]]
        entries.append(entry)

    entries.sort(key=lambda x: x["product_name"])
    return entries[:limit]

def _collect_conflict_snapshot(limit: int = 5) -> dict[str, Any]:
    eng = get_control_engine()
    try:
        with eng.begin() as conn:
            rows = conn.execute(text("""
                SELECT conflict_id, table_name, pk_value, source_db, target_db, created_at
                FROM conflicts
                WHERE status='OPEN'
                ORDER BY created_at DESC
                LIMIT :lim
            """), {"lim": limit}).mappings().all()
            open_count = conn.execute(text("SELECT COUNT(*) FROM conflicts WHERE status='OPEN'")).scalar() or 0
            last_resolved = conn.execute(text("""
                SELECT conflict_id, resolved_at
                FROM conflicts
                WHERE status='RESOLVED'
                ORDER BY resolved_at DESC
                LIMIT 1
            """)).mappings().first()
    except Exception:
        return {"items": [], "open_count": 0, "last_resolved": None}

    items = []
    for row in rows:
        items.append({
            "conflict_id": int(row["conflict_id"]),
            "table_name": row["table_name"],
            "pk_value": row["pk_value"],
            "source_db": row["source_db"],
            "target_db": row["target_db"],
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        })

    return {
        "items": items,
        "open_count": int(open_count),
        "last_resolved": (last_resolved["resolved_at"].isoformat() if last_resolved and last_resolved.get("resolved_at") else None),
    }

@app.get("/dashboard/overview")
def dashboard_overview(limit: int = 8, user=Depends(require_admin)):
    db_stats = {db_key: _fetch_table_counts(db_key) for db_key in get_all_db_keys()}
    product_matrix = _collect_product_matrix(limit)
    conflict_snapshot = _collect_conflict_snapshot(limit)
    total_pending = sum(stat["pending_changes"] for stat in db_stats.values())
    table_volume = _collect_table_volume_totals()
    report = daily_report(user=user)

    if conflict_snapshot["open_count"] > 0:
        note_msg = f"当前有 {conflict_snapshot['open_count']} 条冲突等待处理"
    elif total_pending > 0:
        note_msg = f"{total_pending} 条待同步记录正在排队"
    else:
        note_msg = "同步一切正常"

    notifications = {
        "has_conflict": conflict_snapshot["open_count"] > 0,
        "message": note_msg,
    }

    return {
        "generated_at": utc_now_iso(),
        "db_stats": db_stats,
        "product_matrix": product_matrix,
        "conflicts": conflict_snapshot,
        "pending_changes_total": total_pending,
        "notifications": notifications,
        "report": report,
        "table_volume": table_volume,
    }

# ---------------- Query helpers ----------------
def _run_top_customers_query(db: DBKey, days: int, limit: int) -> dict:
    eng = get_engine(db)
    days = max(1, min(days, 365))
    limit = max(1, min(limit, 50))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    if db == "mssql":
        sql = textwrap.dedent(f"""
            SELECT TOP ({int(limit)}) c.customer_id, c.customer_name, t.total_amount
            FROM customers c
            JOIN (
                SELECT o.customer_id, SUM(oi.quantity * oi.price) AS total_amount
                FROM orders o
                JOIN order_items oi ON oi.order_id = o.order_id
                WHERE o.updated_at >= :cutoff
                GROUP BY o.customer_id
            ) t ON t.customer_id = c.customer_id
            ORDER BY t.total_amount DESC
        """).strip()
        params = {"cutoff": cutoff}
        fetch_limit = None  # already applied via TOP
    else:
        sql = textwrap.dedent("""
            SELECT c.customer_id, c.customer_name, t.total_amount
            FROM customers c
            JOIN (
                SELECT o.customer_id, SUM(oi.quantity * oi.price) AS total_amount
                FROM orders o
                JOIN order_items oi ON oi.order_id = o.order_id
                WHERE o.updated_at >= :cutoff
                GROUP BY o.customer_id
            ) t ON t.customer_id = c.customer_id
            ORDER BY t.total_amount DESC
        """).strip()
        params = {"cutoff": cutoff}
        fetch_limit = limit

    with eng.begin() as conn:
        res = conn.execute(text(sql), params)
        rows = res.mappings().fetchmany(fetch_limit) if fetch_limit else res.mappings().all()

    normalized_rows = []
    for row in rows:
        item = dict(row)
        if item.get("total_amount") is not None:
            item["total_amount"] = float(item["total_amount"])
        normalized_rows.append(item)

    return {"sql": sql, "rows": normalized_rows, "db": db, "days": days, "limit": limit}

def _normalize_sql(sql: str) -> str:
    cleaned = (sql or "").strip()
    if cleaned.endswith(";"):
        cleaned = cleaned.rstrip(" ;\n\t")
    return cleaned

def _ensure_select_sql(sql: str):
    normalized = sql.lstrip().lower()
    if normalized.startswith("with") or normalized.startswith("select"):
        return
    raise HTTPException(status_code=400, detail="目前仅支持 SELECT/CTE 查询")

@app.post("/queries/run")
def run_custom_query(payload: SQLQueryIn = Body(...), user=Depends(require_admin)):
    sql_text = _normalize_sql(payload.sql)
    if not sql_text:
        raise HTTPException(status_code=400, detail="SQL 不能为空")
    _ensure_select_sql(sql_text)
    limit = max(1, min(payload.limit or 200, 1000))
    eng = get_engine(payload.db)
    started = datetime.now(timezone.utc)
    try:
        with eng.begin() as conn:
            result = conn.execute(text(sql_text))
            columns = list(result.keys())
            rows = result.mappings().fetchmany(limit)
    except SQLAlchemyError as exc:
        detail = getattr(exc, "orig", None) or str(exc)
        raise HTTPException(status_code=400, detail=f"SQL 执行失败：{detail}")
    took_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    payload_rows = jsonable_encoder([dict(row) for row in rows])
    truncated = len(rows) >= limit
    return {
        "db": payload.db,
        "sql": sql_text,
        "limit": limit,
        "columns": columns,
        "rows": payload_rows,
        "row_count": len(payload_rows),
        "truncated": truncated,
        "took_ms": round(took_ms, 2),
    }

# ---------------- Complex SQL page (example) ----------------
@app.get("/queries/top-customers")
def top_customers(db: DBKey = Query(...), days: int = 30, limit: int = 10, user=Depends(get_current_user)):
    return _run_top_customers_query(db, days, limit)

@app.get("/ui/query", response_class=HTMLResponse)
def ui_query_page(request: Request, db: DBKey = Query("mysql"), days: int = Query(30, ge=1), limit: int = Query(10, ge=1)):
    data = _run_top_customers_query(db, days, limit)
    return templates.TemplateResponse("query.html", {
        "request": request,
        "db": data["db"],
        "days": data["days"],
        "limit": data["limit"],
        "rows": data["rows"],
        "sql": data["sql"],
    })

# ---------------- Simple UI ----------------
@app.get("/", response_class=HTMLResponse)
def root():
    # 默认入口直接跳转到管理员登录页，符合任务书“进入即可登录”的要求
    return RedirectResponse("/ui/login")

@app.get("/ui", response_class=HTMLResponse)
def ui_root():
    return RedirectResponse("/ui/login")

@app.get("/ui/login", response_class=HTMLResponse)
def ui_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/ui/register", response_class=HTMLResponse)
def ui_register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/ui/data", response_class=HTMLResponse)
def ui_data(request: Request):
    return templates.TemplateResponse("data.html", {"request": request})

@app.get("/ui/conflicts", response_class=HTMLResponse)
def ui_conflicts(request: Request, t: str | None = None):
    # allow token-based view (from email link) for 24h; otherwise require bearer token via Swagger.
    # For simplicity, token-based view is read-only.
    token_ok = False
    if t:
        try:
            verify_conflict_token(t)
            token_ok = True
        except Exception:
            token_ok = False
    return templates.TemplateResponse("conflicts.html", {"request": request, "token_ok": token_ok, "t": t})

@app.get("/ui/conflicts/{conflict_id}", response_class=HTMLResponse)
def ui_conflict_detail(request: Request, conflict_id: int, t: str | None = None):
    token_ok = False
    if t:
        try:
            payload = verify_conflict_token(t)
            token_ok = int(payload.get("conflict_id")) == conflict_id
        except Exception:
            token_ok = False
    return templates.TemplateResponse("conflict_detail.html", {"request": request, "conflict_id": conflict_id, "token_ok": token_ok, "t": t})

@app.get("/ui/report", response_class=HTMLResponse)
def ui_report(request: Request):
    return templates.TemplateResponse("report.html", {"request": request})

@app.get("/ui/dashboard", response_class=HTMLResponse)
def ui_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

# 方便本地直接运行：`python app/main.py`
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=18000, reload=True)
