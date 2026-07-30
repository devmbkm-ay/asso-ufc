from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentMember, RequirePresidentOrAdmin
from app.core.notifications import notify_member
from app.schemas.death_report import DeathReportCreate, DeathReportRead
from models import BeneficiaryDesignation, DeathReport, Member, MemberRole, Role, RoleName

router = APIRouter(prefix="/death-reports", tags=["Signalements"])

# Rôles pouvant instruire un signalement (confirmer/rejeter) ou le déposer
# pour le compte d'un désignateur (sens B) sans être ce désignateur.
ADMIN_ROLES = (RoleName.super_admin, RoleName.president)


def _is_admin(current_member: Member, db: Session) -> bool:
    hit = (
        db.query(Role.name)
        .join(MemberRole, MemberRole.role_id == Role.id)
        .filter(MemberRole.member_id == current_member.id, Role.name.in_(ADMIN_ROLES))
        .first()
    )
    return hit is not None


def _to_read(d: DeathReport, db: Session) -> DeathReportRead:
    reporter = db.query(Member).filter(Member.id == d.reported_by).first()
    reporter_name = f"{reporter.first_name} {reporter.last_name}" if reporter else "—"

    if d.member_id:
        member = db.query(Member).filter(Member.id == d.member_id).first()
        target_label = f"{member.first_name} {member.last_name}" if member else "—"
    else:
        designation = db.query(BeneficiaryDesignation).filter(
            BeneficiaryDesignation.id == d.designation_id
        ).first()
        if designation:
            designator = db.query(Member).filter(Member.id == designation.member_id).first()
            designator_name = f"{designator.first_name} {designator.last_name}" if designator else "—"
            target_label = f"{designation.full_name} ({designation.relation}) — désigné par {designator_name}"
        else:
            target_label = "—"

    return DeathReportRead(
        id=d.id,
        member_id=d.member_id,
        designation_id=d.designation_id,
        target_label=target_label,
        reported_by=d.reported_by,
        reporter_name=reporter_name,
        note=d.note,
        status=d.status,
        reviewed_by=d.reviewed_by,
        reviewed_at=d.reviewed_at,
        created_at=d.created_at,
    )


@router.post("", response_model=DeathReportRead, status_code=status.HTTP_201_CREATED,
             summary="Signaler un décès (membre ou personne désignée)")
def create_death_report(
    payload: DeathReportCreate,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    """
    Sens A (member_id) : tout membre authentifié peut signaler le décès d'un
    autre membre. Sens B (designation_id) : réservé au désignateur lui-même
    (il est seul informé, cf. confidentialité des désignations) ou à un admin
    déjà prévenu autrement.
    """
    if payload.member_id:
        if payload.member_id == current_member.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                 detail="Impossible de signaler son propre décès")
        target_filter = DeathReport.member_id == payload.member_id
    else:
        designation = db.query(BeneficiaryDesignation).filter(
            BeneficiaryDesignation.id == payload.designation_id
        ).first()
        if not designation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Désignation introuvable")
        if designation.member_id != current_member.id and not _is_admin(current_member, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Seul le désignateur ou un administrateur peut signaler le décès d'une personne désignée",
            )
        target_filter = DeathReport.designation_id == payload.designation_id

    existing = db.query(DeathReport).filter(
        target_filter, DeathReport.status == "pending",
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                             detail="Un signalement est déjà en cours pour cette cible")

    d = DeathReport(
        id=uuid4(),
        member_id=payload.member_id,
        designation_id=payload.designation_id,
        reported_by=current_member.id,
        note=payload.note,
        status="pending",
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return _to_read(d, db)


@router.get("", response_model=list[DeathReportRead],
            summary="Liste des signalements de décès (admin)")
def list_death_reports(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    status_filter: Optional[str] = Query(
        None, alias="status", pattern="^(pending|confirmed|dismissed)$",
    ),
    _=RequirePresidentOrAdmin,
):
    """Rôles requis : super_admin, président."""
    q = db.query(DeathReport)
    if status_filter:
        q = q.filter(DeathReport.status == status_filter)
    rows = q.order_by(DeathReport.created_at.desc()).all()
    return [_to_read(d, db) for d in rows]


@router.patch("/{report_id}/confirm", response_model=DeathReportRead,
              summary="Confirmer un signalement de décès")
def confirm_death_report(
    report_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequirePresidentOrAdmin,
):
    """Rôle requis : super_admin, président."""
    d = db.query(DeathReport).filter(DeathReport.id == report_id).first()
    if not d:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signalement introuvable")
    if d.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ce signalement n'est pas en attente")

    d.status = "confirmed"
    d.reviewed_by = current_member.id
    d.reviewed_at = datetime.now(timezone.utc)
    read = _to_read(d, db)
    notify_member(db, d.reported_by, "death_report_confirmed",
                  f"Le signalement concernant {read.target_label} a été confirmé.", "/mon-espace/beneficiaires")
    db.commit()
    db.refresh(d)
    return _to_read(d, db)


@router.patch("/{report_id}/dismiss", response_model=DeathReportRead,
              summary="Rejeter un signalement de décès")
def dismiss_death_report(
    report_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequirePresidentOrAdmin,
):
    """Rôle requis : super_admin, président."""
    d = db.query(DeathReport).filter(DeathReport.id == report_id).first()
    if not d:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signalement introuvable")
    if d.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ce signalement n'est pas en attente")

    d.status = "dismissed"
    d.reviewed_by = current_member.id
    d.reviewed_at = datetime.now(timezone.utc)
    read = _to_read(d, db)
    notify_member(db, d.reported_by, "death_report_dismissed",
                  f"Le signalement concernant {read.target_label} a été rejeté.", "/mon-espace/beneficiaires")
    db.commit()
    db.refresh(d)
    return _to_read(d, db)