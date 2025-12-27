#!/bin/bash
set -e

SQLCMD="/opt/mssql-tools18/bin/sqlcmd"
if [ ! -x "$SQLCMD" ]; then
  SQLCMD="/opt/mssql-tools/bin/sqlcmd"
fi

echo "[mssql-init] waiting for SQL Server..."
for i in {1..60}; do
  "$SQLCMD" -S mssql -U sa -P "$MSSQL_SA_PASSWORD" -C -Q "SELECT 1" >/dev/null 2>&1 && break
  sleep 2
done

echo "[mssql-init] applying schema..."
for i in {1..10}; do
  if "$SQLCMD" -S mssql -U sa -P "$MSSQL_SA_PASSWORD" -C -b -i /scripts/01_schema.sql; then
    break
  fi
  echo "[mssql-init] schema apply failed, retrying ($i/10)..."
  sleep 3
done

echo "[mssql-init] done."
