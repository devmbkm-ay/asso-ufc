from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentMember
from app.schemas.admin_overview import AdminPendingCounts
from models import (
    BeneficiaryDesignation, Contribution, DeathReport, MemberRole, Payment,
    PaymentStatus, Role, RoleName,
)

router = APIRouter(prefix="/admin", tags=["Vue d'ensemble admin"])

# Mêmes rôles que RequirePresidentOrAdmin, utilisés pour valider désignations/signalements.
DESIGNATION_REVIEW_ROLES = {RoleName.super_admin, RoleName.president}
# Mêmes rôles que _can_validate_payment/_can_validate_contribution (cotisations/collectes).
PAYMENT_REVIEW_ROLES = {RoleName.super_admin, RoleName.treasurer, RoleName.secretary, RoleName.president}


@router.get("/pending-counts", response_model=AdminPendingCounts,
            summary="Compteurs d'éléments en attente d'instruction, selon mes rôles")
def get_pending_counts(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    """
    Reflète un état courant (file d'attente), pas un historique — d'où un
    comptage en direct plutôt qu'une notification à marquer comme lue.
    Chaque compteur n'est calculé que si le rôle du membre courant lui
    permet réellement d'agir dessus (cohérent avec les gardes déjà en place
    sur les routes de validation elles-mêmes).
    """
    my_roles = {
        r.name for r in db.query(Role.name)
        .join(MemberRole, MemberRole.role_id == Role.id)
        .filter(MemberRole.member_id == current_member.id)
        .all()
    }

    counts = AdminPendingCounts()

    if my_roles & DESIGNATION_REVIEW_ROLES:
        counts.beneficiaries = db.query(BeneficiaryDesignation).filter(
            BeneficiaryDesignation.status == "pending",
        ).count()
        counts.death_reports = db.query(DeathReport).filter(
            DeathReport.status == "pending",
        ).count()

    if my_roles & PAYMENT_REVIEW_ROLES:
        counts.cotisations = db.query(Payment).filter(
            Payment.status == PaymentStatus.declared,
        ).count()
        counts.collectes = db.query(Contribution).filter(
            Contribution.status == PaymentStatus.declared,
        ).count()

    return counts
