from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Events ────────────────────────────────────────────────────────────────────

class EventCreate(BaseModel):
    title:        str            = Field(..., max_length=300)
    description:  Optional[str] = None
    event_date:   date
    location:     Optional[str] = Field(None, max_length=500)
    capacity:     Optional[int] = Field(None, ge=1)
    ticket_price: Decimal       = Field(Decimal("0"), ge=0, decimal_places=2)


class EventUpdate(BaseModel):
    title:        Optional[str]     = Field(None, max_length=300)
    description:  Optional[str]     = None
    event_date:   Optional[date]    = None
    location:     Optional[str]     = Field(None, max_length=500)
    capacity:     Optional[int]     = Field(None, ge=1)
    ticket_price: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    status:       Optional[str]     = Field(None, pattern="^(draft|published|cancelled|completed)$")


class EventRead(BaseModel):
    id:                 UUID
    title:              str
    description:        Optional[str]
    event_date:         date
    location:           Optional[str]
    capacity:           Optional[int]
    ticket_price:       Decimal
    status:             str
    created_by:         Optional[UUID]
    created_at:         datetime
    registrations_count: int = 0

    model_config = {"from_attributes": True}


# ── Registrations ─────────────────────────────────────────────────────────────

class RegistrationCreate(BaseModel):
    member_id:   UUID
    amount_paid: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)


class RegistrationRead(BaseModel):
    id:            UUID
    event_id:      UUID
    member_id:     UUID
    member_name:   str
    attended:      bool
    amount_paid:   Decimal
    registered_at: datetime

    model_config = {"from_attributes": True}


# ── Rapport de présence ───────────────────────────────────────────────────────

class AttendanceReport(BaseModel):
    event_id:          UUID
    event_title:       str
    event_date:        date
    total_registered:  int
    total_attended:    int
    attendance_rate:   float
    total_revenue:     Decimal
    registrations:     list[RegistrationRead]
