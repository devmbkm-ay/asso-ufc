from datetime import date, timedelta
from decimal import Decimal
from typing import List
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, distinct
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentMember, RequireAdmin, RequireSecretary
from app.schemas.collecte import (
    CollecteCreate, CollecteRead, ContributionCreate, ContributionRead,
)
from models import Collecte, Contribution, Member

router = APIRouter(prefix="/collectes", tags=["Collectes"])

DURATION_DAYS = 14


# ── Helpers ───────────────────────────────────────────────────────────────────

def _collecte_to_read(collecte: Collecte, db: Session) -> CollecteRead:
    today = date.today()
    is_active = (
        not collecte.is_closed
        and collecte.start_date <= today <= collecte.end_date
    )
    total = db.query(
        func.coalesce(func.sum(Contribution.amount), Decimal("0"))
    ).filter(Contribution.collecte_id == collecte.id).scalar()

    count = db.query(
        func.count(distinct(Contribution.member_id))
    ).filter(Contribution.collecte_id == collecte.id).scalar()

    return CollecteRead(
        id=collecte.id,
        title=collecte.title,
        beneficiary_name=collecte.beneficiary_name,
        photo_url=collecte.photo_url,
        description=collecte.description,
        min_amount=collecte.min_amount,
        start_date=collecte.start_date,
        end_date=collecte.end_date,
        is_closed=collecte.is_closed,
        is_active=is_active,
        total_collected=total,
        contributors_count=count,
        created_at=collecte.created_at,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "", response_model=CollecteRead, status_code=status.HTTP_201_CREATED,
    summary="Créer une collecte de solidarité",
)
def create_collecte(
    payload: CollecteCreate,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireSecretary,
):
    """Rôles requis : super_admin, secretary."""
    collecte = Collecte(
        id=uuid4(),
        title=payload.title,
        beneficiary_name=payload.beneficiary_name,
        photo_url=payload.photo_url,
        description=payload.description,
        min_amount=payload.min_amount,
        start_date=payload.start_date,
        end_date=payload.start_date + timedelta(days=DURATION_DAYS),
        created_by=current_member.id,
    )
    db.add(collecte)
    db.commit()
    db.refresh(collecte)
    return _collecte_to_read(collecte, db)


@router.get(
    "", response_model=List[CollecteRead],
    summary="Liste des collectes",
)
def list_collectes(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    active_only: bool = False,
):
    """Retourne toutes les collectes, les actives en premier."""
    query = db.query(Collecte).order_by(Collecte.created_at.desc())
    collectes = query.all()

    result = [_collecte_to_read(c, db) for c in collectes]
    if active_only:
        result = [c for c in result if c.is_active]
    return result


@router.get(
    "/{collecte_id}", response_model=CollecteRead,
    summary="Détail d'une collecte",
)
def get_collecte(
    collecte_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    collecte = db.query(Collecte).filter(Collecte.id == collecte_id).first()
    if not collecte:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collecte introuvable")
    return _collecte_to_read(collecte, db)


@router.post(
    "/{collecte_id}/contributions", response_model=ContributionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Contribuer à une collecte",
)
def contribute(
    collecte_id: UUID,
    payload: ContributionCreate,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    """Tout membre authentifié peut contribuer à une collecte active."""
    collecte = db.query(Collecte).filter(Collecte.id == collecte_id).first()
    if not collecte:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collecte introuvable")

    today = date.today()
    is_active = (
        not collecte.is_closed
        and collecte.start_date <= today <= collecte.end_date
    )
    if not is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cette collecte est clôturée ou expirée",
        )

    if payload.amount < collecte.min_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Le montant minimum est de {collecte.min_amount} €",
        )

    contribution = Contribution(
        id=uuid4(),
        collecte_id=collecte_id,
        member_id=current_member.id,
        amount=payload.amount,
    )
    db.add(contribution)
    db.commit()
    db.refresh(contribution)

    return ContributionRead(
        id=contribution.id,
        collecte_id=contribution.collecte_id,
        member_id=contribution.member_id,
        member_name=f"{current_member.first_name} {current_member.last_name}",
        amount=contribution.amount,
        contributed_at=contribution.contributed_at,
    )


@router.get(
    "/{collecte_id}/contributions", response_model=List[ContributionRead],
    summary="Liste des contributions",
)
def list_contributions(
    collecte_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    collecte = db.query(Collecte).filter(Collecte.id == collecte_id).first()
    if not collecte:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collecte introuvable")

    rows = (
        db.query(Contribution, Member)
        .join(Member, Member.id == Contribution.member_id)
        .filter(Contribution.collecte_id == collecte_id)
        .order_by(Contribution.contributed_at.desc())
        .all()
    )

    return [
        ContributionRead(
            id=c.id,
            collecte_id=c.collecte_id,
            member_id=c.member_id,
            member_name=f"{m.first_name} {m.last_name}",
            amount=c.amount,
            contributed_at=c.contributed_at,
        )
        for c, m in rows
    ]


@router.patch(
    "/{collecte_id}/close", response_model=CollecteRead,
    summary="Clôturer une collecte",
)
def close_collecte(
    collecte_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireAdmin,
):
    """Rôle requis : super_admin."""
    collecte = db.query(Collecte).filter(Collecte.id == collecte_id).first()
    if not collecte:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collecte introuvable")
    if collecte.is_closed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Collecte déjà clôturée")

    collecte.is_closed = True
    db.commit()
    db.refresh(collecte)
    return _collecte_to_read(collecte, db)
