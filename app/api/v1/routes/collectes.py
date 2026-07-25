from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, distinct
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentMember, RequireAdmin, RequireSecretary
from app.core.reconciliation import generate_reference_code
from app.schemas.collecte import (
    CollecteCreate, CollecteUpdate, CollecteRead, ContributionCreate, ContributionRead,
)
from models import Collecte, Contribution, Member, MemberRole, PaymentMethod, PaymentStatus, Role, RoleName

router = APIRouter(prefix="/collectes", tags=["Collectes"])

DURATION_DAYS = 14

# Rôles habilités à voir l'identité réelle des contributeurs anonymes
ADMIN_ROLES = (RoleName.super_admin, RoleName.secretary)

# Rôles habilités à valider/rejeter une contribution déclarée
VALIDATOR_ROLES = (RoleName.super_admin, RoleName.treasurer, RoleName.secretary, RoleName.president)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_admin(current_member: Member, db: Session) -> bool:
    hit = (
        db.query(Role.name)
        .join(MemberRole, MemberRole.role_id == Role.id)
        .filter(MemberRole.member_id == current_member.id, Role.name.in_(ADMIN_ROLES))
        .first()
    )
    return hit is not None


def _can_validate_contribution(db: Session, member_id) -> bool:
    hit = (
        db.query(Role.name)
        .join(MemberRole, MemberRole.role_id == Role.id)
        .filter(MemberRole.member_id == member_id, Role.name.in_(VALIDATOR_ROLES))
        .first()
    )
    return hit is not None


def _contribution_to_read(
    contribution: Contribution, member: Member, current_member: Member, is_admin: bool,
) -> ContributionRead:
    """
    Masque l'identité d'une contribution anonyme sauf pour son auteur ou un admin.
    member_id est masqué en plus de member_name : sinon l'identité reste
    retrouvable via GET /members/{id} malgré le nom affiché "Membre anonyme".
    reference encode les initiales du contributeur, donc elle suit le même
    masquage — sinon une contribution "anonyme" révèle l'identité via sa
    référence affichée à côté du montant public.
    """
    reveal = (not contribution.is_anonymous) or is_admin or (member.id == current_member.id)
    return ContributionRead(
        id=contribution.id,
        collecte_id=contribution.collecte_id,
        member_id=member.id if reveal else None,
        member_name=f"{member.first_name} {member.last_name}" if reveal else "Membre anonyme",
        amount=contribution.amount,
        is_anonymous=contribution.is_anonymous,
        method=contribution.method.value,
        status=contribution.status.value,
        reference=contribution.reference if reveal else None,
        contributed_at=contribution.contributed_at,
    )


def _collecte_to_read(collecte: Collecte, db: Session) -> CollecteRead:
    today = date.today()

    if collecte.is_closed:
        status = "closed"
    elif today < collecte.start_date:
        status = "upcoming"
    elif today <= collecte.end_date:
        status = "active"
    else:
        status = "expired"

    is_active = status == "active"

    # Ne compte que les contributions déclarées ou confirmées : "pending"
    # est une intention de payer, pas de l'argent reçu, donc ne doit pas
    # gonfler le total public affiché.
    counted_statuses = (PaymentStatus.declared, PaymentStatus.confirmed)

    total = db.query(
        func.coalesce(func.sum(Contribution.amount), Decimal("0"))
    ).filter(
        Contribution.collecte_id == collecte.id,
        Contribution.status.in_(counted_statuses),
    ).scalar()

    count = db.query(
        func.count(distinct(Contribution.member_id))
    ).filter(
        Contribution.collecte_id == collecte.id,
        Contribution.status.in_(counted_statuses),
    ).scalar()

    return CollecteRead(
        id=collecte.id,
        title=collecte.title,
        beneficiary_name=collecte.beneficiary_name,
        photo_url=collecte.photo_url,
        description=collecte.description,
        min_amount=collecte.min_amount,
        goal_amount=collecte.goal_amount,
        start_date=collecte.start_date,
        end_date=collecte.end_date,
        is_closed=collecte.is_closed,
        is_active=is_active,
        is_archived=collecte.is_archived,
        archived_at=collecte.archived_at,
        category=collecte.category,
        status=status,
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
        goal_amount=payload.goal_amount,
        start_date=payload.start_date,
        end_date=payload.start_date + timedelta(days=DURATION_DAYS),
        category=payload.category,
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
    include_archived: bool = False,
):
    """Retourne toutes les collectes. Par défaut exclut les archivées."""
    query = db.query(Collecte)
    if not include_archived:
        query = query.filter(Collecte.is_archived == False)  # noqa: E712
    query = query.order_by(Collecte.created_at.desc())
    rows = query.all()

    result = [_collecte_to_read(c, db) for c in rows]
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

    new_id = uuid4()
    contribution = Contribution(
        id=new_id,
        collecte_id=collecte_id,
        member_id=current_member.id,
        amount=payload.amount,
        is_anonymous=payload.is_anonymous,
        method=PaymentMethod(payload.method),
        status=PaymentStatus.pending,
        reference=generate_reference_code(
            current_member.first_name, current_member.last_name, collecte_id, new_id,
        ),
    )
    db.add(contribution)
    db.commit()
    db.refresh(contribution)

    # L'auteur voit toujours sa propre contribution en clair, même anonyme
    # pour les autres — cf. _contribution_to_read (member == current_member).
    return _contribution_to_read(contribution, current_member, current_member, is_admin=False)


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
        .order_by(Contribution.contributed_at.asc())
        .all()
    )

    is_admin = _is_admin(current_member, db)
    return [_contribution_to_read(c, m, current_member, is_admin) for c, m in rows]


@router.post(
    "/{collecte_id}/contributions/{contribution_id}/confirm", response_model=ContributionRead,
    summary="Membre déclare avoir réglé sa contribution",
)
def member_confirm_contribution(
    collecte_id: UUID,
    contribution_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    """Le membre déclare avoir envoyé le paiement (ex: virement Wero effectué)."""
    contribution = db.query(Contribution).filter(
        Contribution.id == contribution_id,
        Contribution.collecte_id == collecte_id,
        Contribution.member_id == current_member.id,
        Contribution.status == PaymentStatus.pending,
    ).first()
    if not contribution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contribution introuvable ou déjà traitée",
        )
    contribution.status = PaymentStatus.declared
    db.commit()
    db.refresh(contribution)
    return _contribution_to_read(contribution, current_member, current_member, is_admin=False)


@router.post(
    "/{collecte_id}/contributions/{contribution_id}/validate", response_model=ContributionRead,
    summary="Trésorier/secrétaire valide la contribution déclarée",
)
def validate_declared_contribution(
    collecte_id: UUID,
    contribution_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    """Rôles requis : super_admin, treasurer, secretary, president."""
    if not _can_validate_contribution(db, current_member.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Réservé au trésorier, secrétaire, président ou super-admin",
        )
    contribution = db.query(Contribution).filter(
        Contribution.id == contribution_id,
        Contribution.collecte_id == collecte_id,
        Contribution.status == PaymentStatus.declared,
    ).first()
    if not contribution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contribution introuvable ou non déclarée",
        )
    contribution.status = PaymentStatus.confirmed
    contribution.recorded_by = current_member.id
    db.commit()
    db.refresh(contribution)
    member = db.query(Member).filter(Member.id == contribution.member_id).first()
    return _contribution_to_read(contribution, member, current_member, is_admin=True)


@router.post(
    "/{collecte_id}/contributions/{contribution_id}/reject", response_model=ContributionRead,
    summary="Trésorier/secrétaire rejette la contribution déclarée",
)
def reject_declared_contribution(
    collecte_id: UUID,
    contribution_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    """Rôles requis : super_admin, treasurer, secretary, president. Renvoie à 'pending'."""
    if not _can_validate_contribution(db, current_member.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Réservé au trésorier, secrétaire, président ou super-admin",
        )
    contribution = db.query(Contribution).filter(
        Contribution.id == contribution_id,
        Contribution.collecte_id == collecte_id,
        Contribution.status == PaymentStatus.declared,
    ).first()
    if not contribution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contribution introuvable ou non déclarée",
        )
    contribution.status = PaymentStatus.pending
    db.commit()
    db.refresh(contribution)
    member = db.query(Member).filter(Member.id == contribution.member_id).first()
    return _contribution_to_read(contribution, member, current_member, is_admin=True)


@router.patch(
    "/{collecte_id}", response_model=CollecteRead,
    summary="Modifier une collecte",
)
def update_collecte(
    collecte_id: UUID,
    payload: CollecteUpdate,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireSecretary,
):
    """Rôles requis : super_admin, secretary."""
    collecte = db.query(Collecte).filter(Collecte.id == collecte_id).first()
    if not collecte:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collecte introuvable")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(collecte, field, value)

    db.commit()
    db.refresh(collecte)
    return _collecte_to_read(collecte, db)


@router.patch(
    "/{collecte_id}/archive", response_model=CollecteRead,
    summary="Archiver une collecte",
)
def archive_collecte(
    collecte_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireAdmin,
):
    """Rôle requis : super_admin. Archive la collecte (exclue de la liste principale)."""
    collecte = db.query(Collecte).filter(Collecte.id == collecte_id).first()
    if not collecte:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collecte introuvable")
    if collecte.is_archived:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Collecte déjà archivée")

    collecte.is_archived = True
    collecte.archived_at = datetime.utcnow()
    db.commit()
    db.refresh(collecte)
    return _collecte_to_read(collecte, db)


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
