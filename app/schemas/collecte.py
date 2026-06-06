from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CollecteCreate(BaseModel):
    title:            str     = Field(..., min_length=1, max_length=300)
    beneficiary_name: str     = Field(..., min_length=1, max_length=200)
    photo_url:        Optional[str] = Field(None, max_length=500)
    description:      Optional[str] = None
    min_amount:       Decimal = Field(Decimal("20.00"), ge=1)
    start_date:       date


class CollecteUpdate(BaseModel):
    title:            Optional[str]     = Field(None, min_length=1, max_length=300)
    beneficiary_name: Optional[str]     = Field(None, min_length=1, max_length=200)
    photo_url:        Optional[str]     = Field(None, max_length=500)
    description:      Optional[str]     = None
    min_amount:       Optional[Decimal] = Field(None, ge=1)


class ContributionCreate(BaseModel):
    amount: Decimal = Field(..., gt=0)


class CollecteRead(BaseModel):
    id:                UUID
    title:             str
    beneficiary_name:  str
    photo_url:         Optional[str] = None
    description:       Optional[str] = None
    min_amount:        Decimal
    start_date:        date
    end_date:          date
    is_closed:         bool
    is_active:         bool
    total_collected:   Decimal
    contributors_count: int
    created_at:        datetime


class ContributionRead(BaseModel):
    id:             UUID
    collecte_id:    UUID
    member_id:      UUID
    member_name:    str
    amount:         Decimal
    contributed_at: datetime
