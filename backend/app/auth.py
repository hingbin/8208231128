from __future__ import annotations
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import text
from .config import settings
from .db import get_control_engine, get_engine, get_all_db_keys

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)

ALGO = "HS256"

def hash_password(pw: str) -> str:
    return pwd_context.hash(pw)

def verify_password(pw: str, pw_hash: str) -> bool:
    return pwd_context.verify(pw, pw_hash)

def create_access_token(sub: str, is_admin: bool, expires_minutes: int = 480) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "is_admin": is_admin,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGO)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGO])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(creds.credentials)
    return payload

def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin required")
    return user

def ensure_admin_seeded() -> None:
    """Make sure the default admin account exists in every DB (mysql/postgres/mssql).

    Previously we only seeded the control_db, so if another DB was wiped it stayed empty
    and the admin row could not be synced. Now we check each DB and insert the admin if
    missing, keeping all three DBs aligned.
    """

    admin_user = "admin"
    admin_pw = "admin123"  # demo default; change in prod
    admin_id = "00000000-0000-0000-0000-000000000001"
    hashed_pw = hash_password(admin_pw)

    for db_key in get_all_db_keys():
        try:
            eng = get_engine(db_key)
        except Exception:
            # If a DB is not ready yet, skip for now; next startup will retry.
            continue

        try:
            with eng.begin() as conn:
                exists = conn.execute(
                    text("SELECT 1 FROM users WHERE username=:u"),
                    {"u": admin_user},
                ).first()
                if exists:
                    continue

                conn.execute(text("""
                    INSERT INTO users(user_id, username, password_hash, role, updated_by_db, row_version)
                    VALUES (:id, :u, :ph, 'admin', :udb, 1)
                """), {
                    "id": admin_id,
                    "u": admin_user,
                    "ph": hashed_pw,
                    "udb": db_key.upper(),
                })
        except Exception:
            # Do not block other DBs if one fails to seed.
            continue
