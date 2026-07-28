from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

CATEGORY_VALUES = {"deces", "mariage", "naissance", "maladie", "autre"}


class CollecteCreate(BaseModel):
    title:            str            = Field(..., min_length=1, max_length=300)
    beneficiary_name: str            = Field(..., min_length=1, max_length=200)
    photo_url:        Optional[str]  = Field(None, max_length=500)
    description:      Optional[str]  = None
    min_amount:       Decimal        = Field(Decimal("20.00"), ge=1)
    goal_amount:      Optional[Decimal] = Field(None, ge=1)
    start_date:       date
    category:         Optional[str]  = None
    # Renseigné quand la collecte répond à un signalement de décès validé
    # (sens A ou B) — pure traçabilité, cf. app/api/v1/routes/death_reports.py.
    beneficiary_designation_id: Optional[UUID] = None


class CollecteUpdate(BaseModel):
    title:            Optional[str]     = Field(None, min_length=1, max_length=300)
    beneficiary_name: Optional[str]     = Field(None, min_length=1, max_length=200)
    photo_url:        Optional[str]     = Field(None, max_length=500)
    description:      Optional[str]     = None
    min_amount:       Optional[Decimal] = Field(None, ge=1)
    goal_amount:      Optional[Decimal] = Field(None, ge=1)
    category:         Optional[str]     = None


class ContributionCreate(BaseModel):
    amount:       Decimal = Field(..., gt=0)
    method:       str     = Field(..., pattern="^(cash|bank_transfer|lydia|sumeria|wero|other)$")
    is_anonymous: bool    = False


class CollecteRead(BaseModel):
    id:                UUID
    title:             str
    beneficiary_name:  str
    photo_url:         Optional[str]      = None
    description:       Optional[str]      = None
    min_amount:        Decimal
    goal_amount:       Optional[Decimal]  = None
    start_date:        date
    end_date:          date
    is_closed:         bool
    is_active:         bool
    is_archived:       bool
    archived_at:       Optional[datetime] = None
    category:          Optional[str]      = None
    # 'upcoming' | 'active' | 'expired' | 'closed'
    status:            str
    total_collected:   Decimal
    contributors_count: int
    created_at:        datetime


class ContributionRead(BaseModel):
    id:             UUID
    collecte_id:    UUID
    # None quand la contribution est anonyme et que le lecteur n'est ni
    # l'auteur ni un admin — évite de pouvoir retrouver l'identité via
    # GET /members/{id} malgré member_name masqué.
    member_id:      Optional[UUID] = None
    member_name:    str
    amount:         Decimal
    is_anonymous:   bool
    method:         str
    status:         str
    # Masqué (None) dans les mêmes conditions que member_id/member_name :
    # la référence encode les initiales, donc elle peut aussi révéler
    # l'identité d'un contributeur anonyme.
    reference:      Optional[str] = None
    contributed_at: datetime
