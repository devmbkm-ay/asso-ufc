from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class BeneficiaryCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=200)
    relation:  str = Field(..., min_length=1, max_length=100)
    contact:   str = Field(..., min_length=1, max_length=200)


class BeneficiaryRead(BaseModel):
    id:             UUID
    member_id:      UUID
    member_name:    str
    member_deceased: bool = False
    full_name:      str
    relation:       str
    contact:        str
    person_deceased: bool = False
    status:         str
    validated_by:   Optional[UUID] = None
    validated_at:   Optional[datetime] = None
    active_from:    Optional[date] = None
    created_at:     datetime
