from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session
from uuid import UUID, uuid4

from app.core.database import get_db
from app.core.deps import CurrentMember
from app.core.security import (
    create_access_token, create_refresh_token,
    decode_token, hash_password, verify_password,
)
from app.core import email as email_svc
from app.schemas.member import (
    LoginRequest, MemberCreate, MemberRead,
    RefreshRequest, RegisterViaInvite, TokenResponse,
)

from models import Member, MemberInvite, MemberRole, Notification, NotificationType, Role, RoleName

router = APIRouter(prefix="/auth", tags=["Auth"])


def _member_to_read(member: Member, roles: list[str]) -> MemberRead:
    # Lit uniquement les colonnes SQL (pas les relations ORM comme `roles`)
    # pour éviter la collision de noms avec MemberRead.roles: list[str].
    cols = {
        attr.key: getattr(member, attr.key)
        for attr in sa_inspect(member.__class__).mapper.column_attrs
    }
    cols["roles"] = roles
    return MemberRead.model_validate(cols)


def _get_member_roles(db: Session, member_id: UUID) -> list[str]:
    rows = (
        db.query(Role.name)
        .join(MemberRole, MemberRole.role_id == Role.id)
        .filter(MemberRole.member_id == member_id)
        .all()
    )
    return [r.name.value for r in rows]


@router.post("/login", response_model=TokenResponse, summary="Connexion")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    member = db.query(Member).filter(Member.email == payload.email).first()
    if not member or not verify_password(payload.password, member.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
        )
    if member.status == "suspended":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte suspendu — contactez l'administrateur",
        )

    roles = _get_member_roles(db, member.id)
    return TokenResponse(
        access_token=create_access_token(member.id, roles),
        refresh_token=create_refresh_token(member.id),
    )


@router.post("/refresh", response_model=TokenResponse, summary="Renouveler le token")
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Refresh token invalide ou expiré",
    )
    try:
        data = decode_token(payload.refresh_token)
        if data.get("type") != "refresh":
            raise credentials_exception
        member_id = data.get("sub")
    except JWTError:
        raise credentials_exception

    member = db.query(Member).filter(Member.id == UUID(member_id)).first()
    if not member:
        raise credentials_exception

    roles = _get_member_roles(db, member.id)
    return TokenResponse(
        access_token=create_access_token(member.id, roles),
        refresh_token=create_refresh_token(member.id),
    )


@router.get("/me", response_model=MemberRead, summary="Profil courant")
def get_me(current_member: CurrentMember, db: Session = Depends(get_db)):
    roles = _get_member_roles(db, current_member.id)
    return _member_to_read(current_member, roles)


@router.post("/register", response_model=MemberRead, status_code=status.HTTP_201_CREATED,
             summary="S'inscrire via un lien d'invitation (public)")
def register_via_invite(payload: RegisterViaInvite, db: Session = Depends(get_db)):
    now = datetime.now(tz=timezone.utc)
    invite = (
        db.query(MemberInvite)
        .filter(
            MemberInvite.token == payload.token,
            MemberInvite.used_at == None,  # noqa: E711
            MemberInvite.expires_at > now,
        )
        .first()
    )
    if not invite:
        raise HTTPException(status_code=400, detail="Lien d'invitation invalide ou expiré")

    if db.query(Member).filter(Member.email == invite.email).first():
        raise HTTPException(status_code=409, detail="Un compte avec cet email existe déjà")

    default_role = db.query(Role).filter(Role.name == RoleName.member).first()

    new_member = Member(
        id=uuid4(),
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=invite.email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        created_by=invite.invited_by,
    )
    db.add(new_member)
    db.flush()

    if default_role:
        db.add(MemberRole(
            id=uuid4(),
            member_id=new_member.id,
            role_id=default_role.id,
            assigned_by=invite.invited_by,
        ))

    invite.used_at = now

    from app.api.v1.routes.members import _init_payments_for_member
    _init_payments_for_member(new_member, db)
    db.commit()
    db.refresh(new_member)

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

    roles = _get_member_roles(db, new_member.id)
    return _member_to_read(new_member, roles)


@router.post("/setup", summary="Créer le premier super-admin (désactivé dès qu'un membre existe)")
def setup_first_admin(payload: MemberCreate, db: Session = Depends(get_db)):
    if db.query(Member).count() > 0:
        raise HTTPException(status_code=403, detail="Setup déjà effectué")

    member_id = uuid4()
    new_member = Member(
        id=member_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        created_by=member_id,
    )
    db.add(new_member)
    db.flush()

    admin_role = db.query(Role).filter(Role.name == RoleName.super_admin).first()
    if admin_role:
        db.add(MemberRole(
            id=uuid4(),
            member_id=new_member.id,
            role_id=admin_role.id,
            assigned_by=new_member.id,
        ))

    db.commit()
    return {"message": "Super-admin créé"}
