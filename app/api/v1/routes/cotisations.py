import csv
import io
import math
from datetime import date
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import get_db
from app.core.deps import CurrentMember, RequireAdmin, RequireTreasurer
from app.schemas.cotisation import (
    CotisationPlanCreate, CotisationPlanRead, CotisationPlanUpdate,
    MonthCell, PaginatedPayments, PaymentCreate, PaymentGridRow,
    PaymentRead, PaymentUpdate, TreasurerDashboard,
)
from models import (
    CotisationFrequency, CotisationPlan, Member, MemberRole, MemberStatus,
    Payment, PaymentMethod, PaymentStatus, Role, RoleName,
)

router = APIRouter(tags=["Cotisations"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _has_treasurer_role(db: Session, member_id) -> bool:
    roles = (
        db.query(Role.name)
        .join(MemberRole, MemberRole.role_id == Role.id)
        .filter(MemberRole.member_id == member_id)
        .all()
    )
    return any(r.name in [RoleName.super_admin, RoleName.treasurer] for r in roles)


def _can_validate_payment(db: Session, member_id) -> bool:
    roles = (
        db.query(Role.name)
        .join(MemberRole, MemberRole.role_id == Role.id)
        .filter(MemberRole.member_id == member_id)
        .all()
    )
    return any(r.name in [RoleName.super_admin, RoleName.treasurer, RoleName.secretary] for r in roles)


def _build_periods(plan: CotisationPlan) -> list[tuple[int | None, int]]:
    end = plan.valid_until or date(plan.valid_from.year, 12, 31)
    periods: list[tuple[int | None, int]] = []
    if plan.frequency == CotisationFrequency.monthly:
        y, m = plan.valid_from.year, plan.valid_from.month
        ey, em = end.year, end.month
        while (y, m) <= (ey, em):
            periods.append((m, y))
            m += 1
            if m > 12:
                m, y = 1, y + 1
    elif plan.frequency == CotisationFrequency.annual:
        end_yr = (plan.valid_until or plan.valid_from).year
        for yr in range(plan.valid_from.year, end_yr + 1):
            periods.append((None, yr))
    else:  # one_time
        periods.append((None, plan.valid_from.year))
    return periods


def _init_payments_for_plan(plan: CotisationPlan, db: Session) -> None:
    """Insert pending payments for all non-suspended members when a plan is created."""
    members = db.query(Member).filter(
        Member.status.in_([MemberStatus.active, MemberStatus.inactive])
    ).all()
    if not members:
        return

    # Query existing entries to avoid duplicates (on_conflict_do_nothing misses NULL period_month)
    existing: set[tuple] = {
        (str(p.member_id), p.period_month, p.period_year)
        for p in db.query(Payment.member_id, Payment.period_month, Payment.period_year)
            .filter(Payment.cotisation_plan_id == plan.id)
            .all()
    }

    today = date.today()
    rows = [
        {
            "id": uuid4(),
            "member_id": member.id,
            "cotisation_plan_id": plan.id,
            "amount": plan.amount,
            "payment_date": today,
            "period_month": pm,
            "period_year": py,
            "method": PaymentMethod.cash,
            "status": PaymentStatus.pending,
            "recorded_by": None,
        }
        for member in members
        for (pm, py) in _build_periods(plan)
        if (str(member.id), pm, py) not in existing
    ]

    if rows:
        db.execute(pg_insert(Payment).values(rows).on_conflict_do_nothing())


def _payment_to_read(p: Payment) -> PaymentRead:
    return PaymentRead(
        id=p.id,
        member_id=p.member_id,
        member_name=f"{p.member.first_name} {p.member.last_name}",
        cotisation_plan_id=p.cotisation_plan_id,
        plan_label=p.cotisation_plan.label,
        amount=p.amount,
        payment_date=p.payment_date,
        period_month=p.period_month,
        period_year=p.period_year,
        method=p.method.value,
        status=p.status.value,
        reference=p.reference,
        notes=p.notes,
    )


# ── Plans de cotisation ───────────────────────────────────────────────────────

@router.get("/cotisation-plans", response_model=list[CotisationPlanRead],
            summary="Liste des plans de cotisation")
def list_plans(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    active_only: bool = Query(True),
):
    q = db.query(CotisationPlan)
    if active_only:
        q = q.filter(CotisationPlan.is_active == True)
    return q.order_by(CotisationPlan.valid_from.desc()).all()


@router.post("/cotisation-plans", response_model=CotisationPlanRead,
             status_code=status.HTTP_201_CREATED,
             summary="Créer un plan de cotisation")
def create_plan(
    payload: CotisationPlanCreate,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireTreasurer,
):
    plan = CotisationPlan(id=uuid4(), **payload.model_dump())
    db.add(plan)
    db.flush()  # assign plan.id before _init_payments_for_plan reads it
    _init_payments_for_plan(plan, db)
    db.commit()
    db.refresh(plan)
    return plan


@router.post("/cotisation-plans/{plan_id}/init-payments",
             status_code=status.HTTP_200_OK,
             summary="Initialiser les cotisations en attente pour tous les membres")
def init_plan_payments(
    plan_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireTreasurer,
):
    plan = db.query(CotisationPlan).filter(CotisationPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan introuvable")
    _init_payments_for_plan(plan, db)
    db.commit()
    return {"detail": "Cotisations initialisées"}


@router.patch("/cotisation-plans/{plan_id}", response_model=CotisationPlanRead,
              summary="Modifier un plan")
def update_plan(
    plan_id: UUID,
    payload: CotisationPlanUpdate,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireTreasurer,
):
    plan = db.query(CotisationPlan).filter(CotisationPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan introuvable")
    # model_dump(exclude_unset=True) : ne retourne que les champs réellement
    # fournis dans la requête PATCH — les champs absents ne sont pas écrasés.
    # setattr(obj, "champ", valeur) est l'équivalent Python de obj.champ = valeur
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    db.commit()
    db.refresh(plan)
    return plan


# ── Paiements ─────────────────────────────────────────────────────────────────

@router.get("/payments", response_model=PaginatedPayments,
            summary="Liste des paiements")
def list_payments(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    member_id: Optional[UUID] = None,
    year: Optional[int] = None,
    month: Optional[int] = Query(None, ge=1, le=12),
    status_filter: Optional[str] = Query(None, alias="status",
                                          pattern="^(pending|declared|confirmed|cancelled)$"),
):
    is_treasurer = _has_treasurer_role(db, current_member.id)
    if not is_treasurer:
        # Members can only query their own payments
        if member_id is None or member_id != current_member.id:
            raise HTTPException(status_code=403, detail="Accès interdit")

    q = db.query(Payment)
    if member_id:
        q = q.filter(Payment.member_id == member_id)
    if year:
        q = q.filter(Payment.period_year == year)
    if month:
        q = q.filter(Payment.period_month == month)
    if status_filter:
        q = q.filter(Payment.status == status_filter)

    total = q.count()
    payments = (
        q.order_by(Payment.payment_date.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return PaginatedPayments(
        items=[_payment_to_read(p) for p in payments],
        total=total,
        page=page,
        size=size,
        pages=math.ceil(total / size) if total else 1,
    )


@router.post("/payments", response_model=PaymentRead,
             status_code=status.HTTP_201_CREATED,
             summary="Enregistrer un paiement")
def create_payment(
    payload: PaymentCreate,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireTreasurer,
):
    member = db.query(Member).filter(Member.id == payload.member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable")

    plan = db.query(CotisationPlan).filter(
        CotisationPlan.id == payload.cotisation_plan_id,
        CotisationPlan.is_active == True,
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan de cotisation introuvable ou inactif")

    payment = Payment(
        id=uuid4(),
        recorded_by=current_member.id,
        **payload.model_dump(),
    )
    db.add(payment)

    if member.status == MemberStatus.inactive:
        member.status = MemberStatus.active

    db.commit()
    db.refresh(payment)
    return _payment_to_read(payment)


# ── Routes statiques /payments/* avant /payments/{id} pour éviter les conflits ─

@router.get("/payments/grid", response_model=list[PaymentGridRow],
            summary="Grille des paiements par membre et par mois")
def payment_grid(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    year: int = Query(default_factory=lambda: date.today().year),
    _=RequireTreasurer,
):
    members = db.query(Member).filter(
        Member.status.in_([MemberStatus.active, MemberStatus.inactive])
    ).order_by(Member.last_name, Member.first_name).all()

    payments = db.query(Payment).filter(
        Payment.period_year == year,
        Payment.period_month.isnot(None),
    ).all()

    index: dict[tuple, Payment] = {
        (str(p.member_id), p.period_month): p for p in payments
    }

    rows = []
    for m in members:
        cells = []
        for month in range(1, 13):
            p = index.get((str(m.id), month))
            cells.append(MonthCell(
                month=month,
                status=p.status.value if p else "none",
                amount=p.amount if p else None,
                payment_id=p.id if p else None,
            ))
        rows.append(PaymentGridRow(
            member_id=m.id,
            member_name=f"{m.first_name} {m.last_name}",
            year=year,
            months=cells,
        ))
    return rows


@router.get("/payments/export", summary="Export CSV des paiements")
def export_payments_csv(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    year: Optional[int] = None,
    _=RequireTreasurer,
):
    q = db.query(Payment).filter(Payment.status == PaymentStatus.confirmed)
    if year:
        q = q.filter(Payment.period_year == year)
    payments = q.order_by(Payment.payment_date.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Membre", "Plan", "Montant (€)",
        "Méthode", "Période", "Statut", "Référence",
    ])
    for p in payments:
        period = f"{p.period_month:02d}/{p.period_year}" if p.period_month else str(p.period_year)
        writer.writerow([
            p.payment_date.isoformat(),
            f"{p.member.first_name} {p.member.last_name}",
            p.cotisation_plan.label,
            float(p.amount),
            p.method.value,
            period,
            p.status.value,
            p.reference or "",
        ])

    output.seek(0)
    filename = f"paiements_{year or 'all'}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/payments/{payment_id}/confirm", response_model=PaymentRead,
             summary="Membre déclare avoir réglé sa cotisation")
def member_confirm_payment(
    payment_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    payment = db.query(Payment).filter(
        Payment.id == payment_id,
        Payment.member_id == current_member.id,
        Payment.status == PaymentStatus.pending,
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Paiement introuvable ou déjà traité")

    payment.status = PaymentStatus.declared

    db.commit()
    db.refresh(payment)
    return _payment_to_read(payment)


@router.post("/payments/{payment_id}/validate", response_model=PaymentRead,
             summary="Trésorier/secrétaire valide la déclaration de paiement")
def validate_declared_payment(
    payment_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    if not _can_validate_payment(db, current_member.id):
        raise HTTPException(status_code=403, detail="Réservé au trésorier, secrétaire ou super-admin")

    payment = db.query(Payment).filter(
        Payment.id == payment_id,
        Payment.status == PaymentStatus.declared,
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Paiement introuvable ou non déclaré")

    payment.status = PaymentStatus.confirmed
    payment.recorded_by = current_member.id

    member = db.query(Member).filter(Member.id == payment.member_id).first()
    if member and member.status == MemberStatus.inactive:
        member.status = MemberStatus.active

    db.commit()
    db.refresh(payment)
    return _payment_to_read(payment)


@router.post("/payments/{payment_id}/reject", response_model=PaymentRead,
             summary="Trésorier/secrétaire rejette la déclaration de paiement")
def reject_declared_payment(
    payment_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    if not _can_validate_payment(db, current_member.id):
        raise HTTPException(status_code=403, detail="Réservé au trésorier, secrétaire ou super-admin")

    payment = db.query(Payment).filter(
        Payment.id == payment_id,
        Payment.status == PaymentStatus.declared,
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Paiement introuvable ou non déclaré")

    payment.status = PaymentStatus.pending

    db.commit()
    db.refresh(payment)
    return _payment_to_read(payment)


# ── Routes paramétrées /payments/{id} ─────────────────────────────────────────

@router.get("/payments/{payment_id}", response_model=PaymentRead,
            summary="Détail d'un paiement")
def get_payment(
    payment_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireTreasurer,
):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Paiement introuvable")
    return _payment_to_read(payment)


@router.patch("/payments/{payment_id}", response_model=PaymentRead,
              summary="Modifier le statut d'un paiement")
def update_payment(
    payment_id: UUID,
    payload: PaymentUpdate,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireTreasurer,
):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Paiement introuvable")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(payment, field, value)
    db.commit()
    db.refresh(payment)
    return _payment_to_read(payment)


@router.delete("/payments/{payment_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Annuler un paiement")
def cancel_payment(
    payment_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireAdmin,
):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Paiement introuvable")
    payment.status = PaymentStatus.cancelled
    db.commit()


# ── Dashboard trésorier ───────────────────────────────────────────────────────

@router.get("/dashboard/treasurer", response_model=TreasurerDashboard,
            summary="Dashboard trésorier")
def treasurer_dashboard(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireTreasurer,
):
    today = date.today()

    total_members  = db.query(Member).count()
    active_members = db.query(Member).filter(Member.status == MemberStatus.active).count()

    # Paiements du mois courant
    monthly = db.query(Payment).filter(
        Payment.period_year == today.year,
        Payment.period_month == today.month,
        Payment.status == PaymentStatus.confirmed,
    )
    paid_this_month    = monthly.count()
    revenue_this_month = monthly.with_entities(func.sum(Payment.amount)).scalar() or 0

    unpaid_this_month = active_members - paid_this_month

    # Revenus depuis le début de l'année
    revenue_ytd = db.query(func.sum(Payment.amount)).filter(
        Payment.period_year == today.year,
        Payment.status == PaymentStatus.confirmed,
    ).scalar() or 0

    pending_count = db.query(Payment).filter(
        Payment.status.in_([PaymentStatus.pending, PaymentStatus.declared]),
    ).count()

    return TreasurerDashboard(
        total_members=total_members,
        active_members=active_members,
        paid_this_month=paid_this_month,
        unpaid_this_month=max(unpaid_this_month, 0),
        revenue_this_month=revenue_this_month,
        revenue_ytd=revenue_ytd,
        pending_count=pending_count,
    )


