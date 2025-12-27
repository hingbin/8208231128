from pydantic import BaseModel, Field
from typing import Optional, Literal

DBKey = Literal["mysql", "postgres", "mssql"]

class LoginIn(BaseModel):
    username: str
    password: str

class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    registration_code: str = Field(min_length=1, max_length=64)

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class ProductIn(BaseModel):
    product_id: Optional[str] = None
    product_name: str = Field(min_length=1, max_length=128)
    price: float = Field(ge=0)
    stock: int = Field(ge=0)

class ProductOut(ProductIn):
    row_version: int
    updated_by_db: str
    updated_at: str | None = None

class ConflictOut(BaseModel):
    conflict_id: int
    table_name: str
    pk_value: str
    source_db: str
    target_db: str
    status: str
    created_at: str
