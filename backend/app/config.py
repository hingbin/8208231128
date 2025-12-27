from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseModel):
    app_env: str = os.getenv("APP_ENV", "dev")
    secret_key: str = os.getenv("APP_SECRET_KEY", "change-me")

    control_db: str = os.getenv("CONTROL_DB", "postgres")  # postgres|mysql|mssql

    mysql_host: str = os.getenv("MYSQL_HOST", "mysql")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_db: str = os.getenv("MYSQL_DB", "syncdb")
    mysql_user: str = os.getenv("MYSQL_USER", "app")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "app_pw")

    postgres_host: str = os.getenv("POSTGRES_HOST", "postgres")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "syncdb")
    postgres_user: str = os.getenv("POSTGRES_USER", "app")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "app_pw")

    mssql_host: str = os.getenv("MSSQL_HOST", "mssql")
    mssql_port: int = int(os.getenv("MSSQL_PORT", "1433"))
    mssql_db: str = os.getenv("MSSQL_DB", "syncdb")
    mssql_user: str = os.getenv("MSSQL_USER", "sa")
    mssql_password: str = os.getenv("MSSQL_PASSWORD", "YourStrong!Passw0rd")

    sync_poll_seconds: int = int(os.getenv("SYNC_POLL_SECONDS", "2"))
    sync_batch_size: int = int(os.getenv("SYNC_BATCH_SIZE", "100"))
    sync_mode: str = os.getenv("SYNC_MODE", "hybrid")
    sync_schedule_interval_seconds: int = int(os.getenv("SYNC_SCHEDULE_INTERVAL_SECONDS", "300"))
    sync_schedule_max_rounds: int = int(os.getenv("SYNC_SCHEDULE_MAX_ROUNDS", "5"))
    admin_registration_code: str = os.getenv("ADMIN_REGISTRATION_CODE", "aaa")

    smtp_host: str = os.getenv("SMTP_HOST", "mailhog")
    smtp_port: int = int(os.getenv("SMTP_PORT", "1025"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    email_from: str = os.getenv("EMAIL_FROM", "sync-platform@example.com")
    email_admin_to: str = os.getenv("EMAIL_ADMIN_TO", "admin@example.com")
    resend_api_key: str = os.getenv("RESEND_API_KEY", "re_8Th4yY1r_2TNJt2ktWhwsEVra2h55t1W5")

    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:18000")

settings = Settings()
