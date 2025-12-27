from __future__ import annotations
import time
from datetime import datetime
from sqlalchemy import text
from ..config import settings
from ..db import get_engine, get_all_db_keys
from .replicator import apply_change_to_targets, mark_processed

def fetch_changes(eng, batch: int, db_key: str):
    with eng.begin() as conn:
        if db_key == "mssql":
            # TOP does not accept parameter placeholders reliably in SQL Server,
            # so embed the (sanitized) batch size directly.
            sql = f"""
                SELECT TOP ({int(batch)}) change_id, table_name, pk_value, op_type, row_data, source_db, created_at
                FROM change_log
                WHERE processed=0
                ORDER BY change_id
            """
            rows = conn.execute(text(sql)).mappings().all()
            return rows
        else:
            sql = """
                SELECT change_id, table_name, pk_value, op_type, row_data, source_db, created_at
                FROM change_log
                WHERE processed=0
                ORDER BY change_id
                LIMIT :lim
            """
        rows = conn.execute(text(sql), {"lim": batch}).mappings().all()
    return rows

def _process_db_changes(db_key: str, batch: int) -> int:
    eng = get_engine(db_key)
    try:
        changes = fetch_changes(eng, batch, db_key)
    except Exception as exc:
        print(f"[worker] fetch error db={db_key}: {exc}")
        return 0

    processed = 0
    for ch in changes:
        try:
            source_db = (ch["source_db"] or db_key).lower()
            apply_change_to_targets(source_db, dict(ch))
            mark_processed(eng, int(ch["change_id"]))
            processed += 1
        except Exception as exc:
            print(f"[worker] apply error change_id={ch.get('change_id')} db={db_key}: {exc}")
            # best effort: do not mark processed so it can retry
    return processed

def _process_all_dbs(batch: int) -> int:
    total = 0
    for db_key in get_all_db_keys():
        total += _process_db_changes(db_key, batch)
    return total

def _run_schedule_cycle(max_rounds: int) -> int:
    max_rounds = max(1, max_rounds)
    total = 0
    for _ in range(max_rounds):
        processed = _process_all_dbs(settings.sync_batch_size)
        total += processed
        if processed == 0:
            break
    return total

def run_forever():
    poll = max(1, settings.sync_poll_seconds)
    batch = settings.sync_batch_size
    mode = (settings.sync_mode or "hybrid").strip().lower()
    if mode not in {"realtime", "schedule", "hybrid"}:
        mode = "hybrid"

    schedule_enabled = mode in ("schedule", "hybrid")
    realtime_enabled = mode in ("realtime", "hybrid")
    schedule_interval = max(1, settings.sync_schedule_interval_seconds)
    next_schedule = time.time() + schedule_interval if schedule_enabled else None

    print(
        "[worker] starting "
        f"(mode={mode} poll={poll}s batch={batch} "
        f"schedule_every={schedule_interval if schedule_enabled else 'n/a'}s)"
    )

    while True:
        work_done = 0
        if realtime_enabled:
            processed = _process_all_dbs(batch)
            work_done += processed
            if processed:
                print(f"[worker] realtime replicated {processed} change(s)")

        if schedule_enabled and next_schedule is not None and time.time() >= next_schedule:
            print(f"[worker] scheduled sync triggered at {datetime.utcnow().isoformat()}Z")
            processed = _run_schedule_cycle(settings.sync_schedule_max_rounds)
            work_done += processed
            print(f"[worker] scheduled sync finished rows={processed}")
            next_schedule = time.time() + schedule_interval

        if work_done == 0:
            if realtime_enabled:
                time.sleep(poll)
            elif schedule_enabled and next_schedule is not None:
                sleep_for = max(1, next_schedule - time.time())
                time.sleep(sleep_for)
            else:
                time.sleep(poll)

if __name__ == "__main__":
    run_forever()
