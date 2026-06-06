import math
from typing import Annotated, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentMember, RequireAdmin, RequireSecretary
from app.core.security import hash_password
from app.core import email as email_svc
from app.schemas.member import (
    MemberCreate, MemberListItem, MemberRead,
    MemberStatusUpdate, MemberUpdate, PaginatedMembers,
)

from models import AuditLog, Member, MemberRole, Notification, NotificationType, Role, RoleName

router = APIRouter(prefix="/members", tags=["Membres"])


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, pattern="^(active|inactive|suspended|honorary)$"),
    search: Optional[str] = Query(None, max_length=100),
    _: Member = RequireSecretary,
):
    """
    Liste paginée des membres avec filtres optionnels.
    Rôles requis : super_admin, secretary.
    """
    query = db.query(Member)

    if status:
        query = query.filter(Member.status == status)
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
        item = MemberListItem.model_validate(m)
        item.roles = _get_roles(db, m.id)
        items.append(item)

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
        if not roles.intersection({"super_admin", "secretary", "treasurer"}):
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
    Les admins/secrétaires peuvent modifier n'importe quel profil.
    """
    roles = set(_get_roles(db, current_member.id))
    is_privileged = bool(roles.intersection({"super_admin", "secretary"}))

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
    _: Member = RequireAdmin,
):
    """Rôle requis : super_admin uniquement."""
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Membre introuvable")

    before_status = str(member.status)
    member.status = payload.status
    _audit(db, current_member.id, "member.status_change", member_id,
           {"before": {"status": before_status}, "after": {"status": payload.status}})
    db.commit()
    db.refresh(member)
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
