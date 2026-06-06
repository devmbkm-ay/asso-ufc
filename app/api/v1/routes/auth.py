from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy.orm import Session
from uuid import UUID, uuid4

from app.core.database import get_db
from app.core.deps import CurrentMember
from app.core.security import (
    create_access_token, create_refresh_token,
    decode_token, hash_password, verify_password,
)
from app.schemas.member import LoginRequest, MemberCreate, MemberRead, RefreshRequest, TokenResponse

from models import Member, MemberRole, Role, RoleName

router = APIRouter(prefix="/auth", tags=["Auth"])


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
    result = MemberRead.model_validate(current_member, use_enum_values=True)
    result.roles = roles
    return result


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
