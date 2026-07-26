import math
from datetime import date
from typing import Annotated, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentMember, RequireAdmin, RequirePresidentOrAdmin, RequireSecretary
from app.core.security import hash_password
from app.core import email as email_svc
from app.schemas.member import (
    MemberCreate, MemberListItem, MemberRead,
    MemberStatusUpdate, MemberUpdate, PaginatedMembers, RoleAssign,
)

from models import (
    AuditLog, CotisationFrequency, CotisationPlan, Member, MemberRole,
    Notification, NotificationType, Payment, PaymentMethod, PaymentStatus,
    Role, RoleName,
)

router = APIRouter(prefix="/members", tags=["Membres"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _init_payments_for_member(member: Member, db: Session) -> None:
    """Create pending payments for a new member on all currently active plans."""
    plans = db.query(CotisationPlan).filter(CotisationPlan.is_active == True).all()
    if not plans:
        return

    today = date.today()
    rows = []
    for plan in plans:
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
            for yr in range(plan.valid_from.year, end.year + 1):
                periods.append((None, yr))
        else:  # one_time
            periods.append((None, plan.valid_from.year))

        for pm, py in periods:
            rows.append({
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
            })

    if rows:
        db.execute(pg_insert(Payment).values(rows).on_conflict_do_nothing())


def _get_roles(db: Session, member_id: UUID) -> list[str]:
    rows = (
        db.query(Role.name)
        .join(MemberRole, MemberRole.role_id == Role.id)
        .filter(MemberRole.member_id == member_id)
        .all()
    )
    return [r.name.value for r in rows]


def _audit(db: Session, actor_id: UUID, action: str, record_id: UUID, diff: dict):
    db.add(AuditLog(
        id=uuid4(),
        actor_id=actor_id,
        action=action,
        table_name="members",
        record_id=record_id,
        diff=diff,
    ))


def _member_to_read(member: Member, roles: list[str]) -> MemberRead:
    cols = {
        attr.key: getattr(member, attr.key)
        for attr in sa_inspect(member.__class__).mapper.column_attrs
    }
    cols["roles"] = roles
    return MemberRead.model_validate(cols)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=PaginatedMembers, summary="Liste des membres")
def list_members(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=500),
    status: Optional[str] = Query(None, pattern="^(active|inactive|suspended|honorary|pending)$"),
    search: Optional[str] = Query(None, max_length=100),
):
    """
    Liste paginée des membres.
    Tous les membres authentifiés peuvent lister les membres actifs.
    Secrétaire / président / super_admin : accès à tous les statuts.
    """
    roles = set(_get_roles(db, current_member.id))
    is_privileged = bool(roles.intersection({"super_admin", "secretary", "president"}))

    query = db.query(Member)

    if is_privileged:
        if status:
            query = query.filter(Member.status == status)
    else:
        # Membres ordinaires : actifs uniquement, quel que soit le filtre demandé
        query = query.filter(Member.status == "active")

    if search:
        term = f"%{search.lower()}%"
        query = query.filter(
            (Member.first_name.ilike(term)) |
            (Member.last_name.ilike(term))  |
            (Member.email.ilike(term))
        )

    total = query.count()
    members = (
        query
        .order_by(Member.last_name, Member.first_name)
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    items = []
    for m in members:
        cols = {
            attr.key: getattr(m, attr.key)
            for attr in sa_inspect(m.__class__).mapper.column_attrs
        }
        cols["roles"] = _get_roles(db, m.id)
        items.append(MemberListItem.model_validate(cols))

    return PaginatedMembers(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=math.ceil(total / size) if total else 1,
    )


@router.post("", response_model=MemberRead, status_code=status.HTTP_201_CREATED,
             summary="Créer un membre")
def create_member(
    payload: MemberCreate,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _: Member = RequireSecretary,
):
    if db.query(Member).filter(Member.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un membre avec cet email existe déjà",
        )

    # Récupère le rôle "member" par défaut
    default_role = db.query(Role).filter(Role.name == RoleName.member).first()

    new_member = Member(
        id=uuid4(),
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
        birth_date=payload.birth_date,
        password_hash=hash_password(payload.password),
        created_by=current_member.id,
    )
    db.add(new_member)
    db.flush()  # obtenir l'ID avant le commit

    if default_role:
        db.add(MemberRole(
            id=uuid4(),
            member_id=new_member.id,
            role_id=default_role.id,
            assigned_by=current_member.id,
        ))

    _audit(db, current_member.id, "member.create", new_member.id,
           {"after": {"email": payload.email, "name": f"{payload.first_name} {payload.last_name}"}})

    _init_payments_for_member(new_member, db)
    db.commit()
    db.refresh(new_member)

    # Email de bienvenue — non bloquant si Brevo non configuré
    from datetime import datetime, timezone
    ok = email_svc.send_welcome(new_member.email, new_member.first_name)
    db.add(Notification(
        id=uuid4(),
        member_id=new_member.id,
        type=NotificationType.welcome,
        subject="Bienvenue dans l'association !",
        body="",
        sent=ok,
        sent_at=datetime.now(tz=timezone.utc) if ok else None,
    ))
    db.commit()

    return _member_to_read(new_member, _get_roles(db, new_member.id))


@router.get("/{member_id}", response_model=MemberRead, summary="Détail d'un membre")
def get_member(
    member_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    """
    Un membre peut voir son propre profil.
    Les admins/secrétaires voient tous les profils.
    """
    if current_member.id != member_id:
        # Vérifie qu'il a un rôle suffisant
        roles = set(_get_roles(db, current_member.id))
        if not roles.intersection({"super_admin", "secretary", "treasurer", "president"}):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Accès non autorisé")

    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Membre introuvable")
    return _member_to_read(member, _get_roles(db, member.id))


@router.patch("/{member_id}", response_model=MemberRead, summary="Modifier un membre")
def update_member(
    member_id: UUID,
    payload: MemberUpdate,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    """
    Un membre peut modifier son propre profil.
    Les admins/secrétaires/président peuvent modifier n'importe quel profil.
    """
    roles = set(_get_roles(db, current_member.id))
    is_privileged = bool(roles.intersection({"super_admin", "secretary", "president"}))

    if current_member.id != member_id and not is_privileged:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Accès non autorisé")

    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Membre introuvable")

    before = {k: str(getattr(member, k)) for k in payload.model_fields_set}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(member, field, value)
    after = {k: str(getattr(member, k)) for k in payload.model_fields_set}

    _audit(db, current_member.id, "member.update", member_id, {"before": before, "after": after})
    db.commit()
    db.refresh(member)
    return _member_to_read(member, _get_roles(db, member.id))


@router.patch("/{member_id}/status", response_model=MemberRead, summary="Changer le statut")
def update_member_status(
    member_id: UUID,
    payload: MemberStatusUpdate,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _: Member = RequirePresidentOrAdmin,
):
    """Rôle requis : super_admin ou président."""
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Membre introuvable")

    before_status = str(member.status)
    member.status = payload.status
    _audit(db, current_member.id, "member.status_change", member_id,
           {"before": {"status": before_status}, "after": {"status": payload.status}})

    # Approbation d'une auto-inscription via code d'adhésion : c'est ici que le
    # membre devient réellement actif, donc c'est ici (et non à l'inscription)
    # qu'on initialise ses cotisations et qu'on envoie l'email de bienvenue.
    if before_status == "pending" and payload.status == "active":
        _init_payments_for_member(member, db)
        from datetime import datetime, timezone
        ok = email_svc.send_welcome(member.email, member.first_name)
        db.add(Notification(
            id=uuid4(),
            member_id=member.id,
            type=NotificationType.welcome,
            subject="Bienvenue dans l'association !",
            body="",
            sent=ok,
            sent_at=datetime.now(tz=timezone.utc) if ok else None,
        ))

    db.commit()
    db.refresh(member)
    return _member_to_read(member, _get_roles(db, member.id))


@router.post("/{member_id}/roles", response_model=MemberRead,
             status_code=status.HTTP_201_CREATED,
             summary="Attribuer un rôle à un membre")
def assign_role(
    member_id: UUID,
    payload: RoleAssign,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireAdmin,
):
    """Rôle requis : super_admin."""
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable")

    role = db.query(Role).filter(Role.name == payload.role_name).first()
    if not role:
        raise HTTPException(status_code=400, detail="Rôle invalide")

    existing = db.query(MemberRole).filter(
        MemberRole.member_id == member_id,
        MemberRole.role_id == role.id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Ce rôle est déjà attribué")

    db.add(MemberRole(
        id=uuid4(),
        member_id=member_id,
        role_id=role.id,
        assigned_by=current_member.id,
    ))
    _audit(db, current_member.id, "member.role_assign", member_id, {"role": payload.role_name})
    db.commit()
    db.refresh(member)
    return _member_to_read(member, _get_roles(db, member.id))


@router.delete("/{member_id}/roles/{role_name}", response_model=MemberRead,
               summary="Révoquer un rôle d'un membre")
def revoke_role(
    member_id: UUID,
    role_name: str,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireAdmin,
):
    """Rôle requis : super_admin."""
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable")

    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        raise HTTPException(status_code=400, detail="Rôle invalide")

    member_role = db.query(MemberRole).filter(
        MemberRole.member_id == member_id,
        MemberRole.role_id == role.id,
    ).first()
    if not member_role:
        raise HTTPException(status_code=404, detail="Ce rôle n'est pas attribué à ce membre")

    db.delete(member_role)
    _audit(db, current_member.id, "member.role_revoke", member_id, {"role": role_name})
    db.commit()
    return _member_to_read(member, _get_roles(db, member.id))


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Supprimer un membre")
def delete_member(
    member_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _: Member = RequireAdmin,
):
    """
    Soft delete : passe le statut à 'inactive'.
    La suppression physique n'est pas exposée via l'API.
    Rôle requis : super_admin.
    """
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Membre introuvable")
    if member_id == current_member.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Vous ne pouvez pas supprimer votre propre compte")

    member.status = "inactive"
    _audit(db, current_member.id, "member.delete", member_id,
           {"before": {"status": "active"}, "after": {"status": "inactive"}})
    db.commit()
