from __future__ import annotations
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from .config import settings

def mysql_url() -> str:
    return f"mysql+pymysql://{settings.mysql_user}:{settings.mysql_password}@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_db}?charset=utf8mb4"

def pg_url() -> str:
    return f"postgresql+psycopg2://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"

def mssql_url() -> str:
    # ODBC Driver 18 inside container; TrustServerCertificate to avoid TLS issues in dev
    driver = "ODBC Driver 18 for SQL Server"
    return (
        f"mssql+pyodbc://{settings.mssql_user}:{settings.mssql_password}"
        f"@{settings.mssql_host}:{settings.mssql_port}/{settings.mssql_db}"
        f"?driver={driver.replace(' ', '+')}&TrustServerCertificate=yes"
    )

_engines: dict[str, Engine] = {}

def get_engine(db_key: str) -> Engine:
    db_key = db_key.lower()
    if db_key in _engines:
        return _engines[db_key]

    if db_key == "mysql":
        url = mysql_url()
    elif db_key in ("postgres", "pg"):
        url = pg_url()
        db_key = "postgres"
    elif db_key in ("mssql", "sqlserver"):
        url = mssql_url()
        db_key = "mssql"
    else:
        raise ValueError(f"Unknown db_key: {db_key}")

    eng = create_engine(url, pool_pre_ping=True, future=True)
    _engines[db_key] = eng
    return eng

def get_all_db_keys() -> list[str]:
    return ["mysql", "postgres", "mssql"]

def get_control_engine() -> Engine:
    return get_engine(settings.control_db)
