from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Cotisation Plans ──────────────────────────────────────────────────────────

class CotisationPlanCreate(BaseModel):
    label:       str     = Field(..., max_length=200)
    amount:      Decimal = Field(..., gt=0, decimal_places=2)
    frequency:   str     = Field(..., pattern="^(monthly|annual|one_time)$")
    valid_from:  date
    valid_until: Optional[date] = None


class CotisationPlanUpdate(BaseModel):
    label:       Optional[str]     = Field(None, max_length=200)
    amount:      Optional[Decimal] = Field(None, gt=0, decimal_places=2)
    valid_until: Optional[date]    = None
    is_active:   Optional[bool]    = None


class CotisationPlanRead(BaseModel):
    id:          UUID
    label:       str
    amount:      Decimal
    frequency:   str
    valid_from:  date
    valid_until: Optional[date]
    is_active:   bool

    model_config = {"from_attributes": True}


# ── Payments ──────────────────────────────────────────────────────────────────

class PaymentCreate(BaseModel):
    member_id:          UUID
    cotisation_plan_id: UUID
    amount:             Decimal = Field(..., gt=0, decimal_places=2)
    payment_date:       date    = Field(default_factory=date.today)
    period_month:       Optional[int] = Field(None, ge=1, le=12)
    period_year:        int     = Field(..., ge=2000, le=2100)
    method:             str     = Field("cash", pattern="^(cash|bank_transfer|lydia|sumeria|paypal|other)$")
    reference:          Optional[str] = Field(None, max_length=200)
    notes:              Optional[str] = None


class PaymentUpdate(BaseModel):
    status:    Optional[str]  = Field(None, pattern="^(pending|confirmed|cancelled)$")
    reference: Optional[str]  = Field(None, max_length=200)
    notes:     Optional[str]  = None


class PaymentRead(BaseModel):
    id:                 UUID
    member_id:          UUID
    member_name:        str
    member_deceased:    bool = False
    cotisation_plan_id: UUID
    plan_label:         str
    amount:             Decimal
    payment_date:       date
    period_month:       Optional[int]
    period_year:        int
    method:             str
    status:             str
    reference:          Optional[str]
    proof_url:          Optional[str] = None
    notes:              Optional[str]

    model_config = {"from_attributes": True}


class PaginatedPayments(BaseModel):
    items: list[PaymentRead]
    total: int
    page:  int
    size:  int
    pages: int


# ── Dashboard trésorier ───────────────────────────────────────────────────────

class TreasurerDashboard(BaseModel):
    total_members:       int
    active_members:      int
    paid_this_month:     int
    unpaid_this_month:   int
    revenue_this_month:  Decimal
    revenue_ytd:         Decimal
    pending_count:       int
    active_members_7d:   int
    active_members_30d:  int
    never_logged_in:     int


# ── Grille mensuelle ──────────────────────────────────────────────────────────

class MonthCell(BaseModel):
    month:      int
    status:     str    # "paid" | "pending" | "cancelled" | "none"
    amount:     Optional[Decimal]
    payment_id: Optional[UUID]


class PaymentGridRow(BaseModel):
    member_id:   UUID
    member_name: str
    year:        int
    months:      list[MonthCell]  # 12 cellules
