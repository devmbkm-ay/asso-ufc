from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentMember, RequirePresidentOrAdmin
from app.core.notifications import notify_member
from app.schemas.beneficiary import BeneficiaryCreate, BeneficiaryRead
from models import BeneficiaryDesignation, DeathReport, Member, MemberStatus

router = APIRouter(prefix="/beneficiaries", tags=["Bénéficiaires"])

MAX_BENEFICIARIES = 2
GRACE_PERIOD_DAYS = 30

# Statuts qui comptent comme une désignation active (occupent une des 2 places)
ACTIVE_STATUSES = ("pending", "validated")


def _to_read(d: BeneficiaryDesignation, db: Session) -> BeneficiaryRead:
    member = db.query(Member).filter(Member.id == d.member_id).first()
    person_deceased = db.query(DeathReport).filter(
        DeathReport.designation_id == d.id,
        DeathReport.status == "confirmed",
    ).first() is not None
    return BeneficiaryRead(
        id=d.id,
        member_id=d.member_id,
        member_name=f"{member.first_name} {member.last_name}" if member else "—",
        member_deceased=bool(member and member.status == MemberStatus.deceased),
        full_name=d.full_name,
        relation=d.relation,
        contact=d.contact,
        person_deceased=person_deceased,
        status=d.status,
        validated_by=d.validated_by,
        validated_at=d.validated_at,
        active_from=d.active_from,
        created_at=d.created_at,
    )


@router.get("/me", response_model=list[BeneficiaryRead],
            summary="Mes bénéficiaires désignés")
def list_my_beneficiaries(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    rows = (
        db.query(BeneficiaryDesignation)
        .filter(
            BeneficiaryDesignation.member_id == current_member.id,
            BeneficiaryDesignation.status != "revoked",
        )
        .order_by(BeneficiaryDesignation.created_at)
        .all()
    )
    return [_to_read(d, db) for d in rows]


@router.post("/me", response_model=BeneficiaryRead, status_code=status.HTTP_201_CREATED,
             summary="Désigner un bénéficiaire")
def create_my_beneficiary(
    payload: BeneficiaryCreate,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    """Tout membre authentifié peut désigner jusqu'à 2 bénéficiaires — l'éligibilité
    réelle (a-t-il déjà perdu ses parents proches) se vérifie humainement par
    l'admin au moment de la validation, pas par une règle automatique."""
    active_count = db.query(BeneficiaryDesignation).filter(
        BeneficiaryDesignation.member_id == current_member.id,
        BeneficiaryDesignation.status.in_(ACTIVE_STATUSES),
    ).count()
    if active_count >= MAX_BENEFICIARIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Vous avez déjà désigné le nombre maximum de bénéficiaires ({MAX_BENEFICIARIES})",
        )

    d = BeneficiaryDesignation(
        id=uuid4(),
        member_id=current_member.id,
        full_name=payload.full_name,
        relation=payload.relation,
        contact=payload.contact,
        status="pending",
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return _to_read(d, db)


@router.delete("/me/{designation_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Révoquer un de mes bénéficiaires")
def revoke_my_beneficiary(
    designation_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    d = db.query(BeneficiaryDesignation).filter(
        BeneficiaryDesignation.id == designation_id,
        BeneficiaryDesignation.member_id == current_member.id,
    ).first()
    if not d:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Désignation introuvable")
    d.status = "revoked"
    db.commit()


@router.get("", response_model=list[BeneficiaryRead],
            summary="Liste des bénéficiaires désignés (admin)")
def list_beneficiaries(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    status_filter: Optional[str] = Query(
        None, alias="status", pattern="^(pending|validated|rejected|revoked)$",
    ),
    member_id: Optional[UUID] = Query(None),
    _=RequirePresidentOrAdmin,
):
    """Rôles requis : super_admin, président. Réservé à l'instruction des
    dossiers — les noms/coordonnées des bénéficiaires ne sont jamais publics."""
    q = db.query(BeneficiaryDesignation)
    if status_filter:
        q = q.filter(BeneficiaryDesignation.status == status_filter)
    if member_id:
        q = q.filter(BeneficiaryDesignation.member_id == member_id)
    rows = q.order_by(BeneficiaryDesignation.created_at).all()
    return [_to_read(d, db) for d in rows]


@router.patch("/{designation_id}/validate", response_model=BeneficiaryRead,
              summary="Valider une désignation")
def validate_beneficiary(
    designation_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequirePresidentOrAdmin,
):
    """Rôle requis : super_admin, président."""
    d = db.query(BeneficiaryDesignation).filter(BeneficiaryDesignation.id == designation_id).first()
    if not d:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Désignation introuvable")
    if d.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cette désignation n'est pas en attente")

    d.status = "validated"
    d.validated_by = current_member.id
    d.validated_at = datetime.now(timezone.utc)
    d.active_from = date.today() + timedelta(days=GRACE_PERIOD_DAYS)
    notify_member(db, d.member_id, "designation_validated",
                  f"Votre désignation de {d.full_name} a été validée.", "/mon-espace/beneficiaires")
    db.commit()
    db.refresh(d)
    return _to_read(d, db)


@router.patch("/{designation_id}/reject", response_model=BeneficiaryRead,
              summary="Rejeter une désignation")
def reject_beneficiary(
    designation_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequirePresidentOrAdmin,
):
    """Rôle requis : super_admin, président."""
    d = db.query(BeneficiaryDesignation).filter(BeneficiaryDesignation.id == designation_id).first()
    if not d:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Désignation introuvable")
    if d.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cette désignation n'est pas en attente")

    d.status = "rejected"
    d.validated_by = current_member.id
    d.validated_at = datetime.now(timezone.utc)
    notify_member(db, d.member_id, "designation_rejected",
                  f"Votre désignation de {d.full_name} a été rejetée.", "/mon-espace/beneficiaires")
    db.commit()
    db.refresh(d)
    return _to_read(d, db)
