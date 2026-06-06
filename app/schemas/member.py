from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=72)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Member ────────────────────────────────────────────────────────────────────

class MemberBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name:  str = Field(..., min_length=1, max_length=100)
    email:      EmailStr
    phone:      Optional[str] = Field(None, max_length=30)
    address:    Optional[str] = Field(None, max_length=500)
    birth_date: Optional[date] = None


class MemberCreate(MemberBase):
    password: str = Field(..., min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("Le mot de passe doit contenir au moins un chiffre")
        return v


class MemberUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name:  Optional[str] = Field(None, min_length=1, max_length=100)
    phone:      Optional[str] = Field(None, max_length=30)
    address:    Optional[str] = Field(None, max_length=500)
    birth_date: Optional[date] = None


class MemberStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(active|inactive|suspended|honorary)$")


class MemberRead(MemberBase):
    id:         UUID
    joined_at:  date
    status:     str
    created_at: datetime
    updated_at: datetime
    roles:      list[str] = []

    model_config = {"from_attributes": True, "use_enum_values": True}

    @model_validator(mode="before")
    @classmethod
    def _clear_orm_roles(cls, data: Any) -> Any:
        # Quand Pydantic lit un objet SQLAlchemy, member.roles retourne la
        # relation ORM (list[MemberRole]) au lieu de list[str]. On l'efface
        # via __dict__ pour éviter le lazy-load et utiliser le défaut [].
        # Les appelants assignent ensuite roles manuellement.
        if hasattr(data, "__tablename__"):
            data.__dict__.pop("roles", None)
        return data


class MemberListItem(BaseModel):
    id:        UUID
    first_name: str
    last_name:  str
    email:      EmailStr
    status:     str
    joined_at:  date
    roles:      list[str] = []

    model_config = {"from_attributes": True}


class PaginatedMembers(BaseModel):
    items: list[MemberListItem]
    total: int
    page:  int
    size:  int
    pages: int
