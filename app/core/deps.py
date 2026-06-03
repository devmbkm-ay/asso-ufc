from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from models import Member, MemberRole, Role, RoleName

bearer_scheme = HTTPBearer()


# ── Résolution du membre courant ──────────────────────────────────────────────

def get_current_member(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Session = Depends(get_db),
) -> Member:
    """
    Valide le JWT et retourne le membre correspondant.
    Utilisé comme dépendance dans toutes les routes protégées.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise credentials_exception
        member_id: str = payload.get("sub")
        if not member_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    member = db.query(Member).filter(Member.id == UUID(member_id)).first()
    if not member:
        raise credentials_exception
    if member.status == "suspended":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte suspendu",
        )
    return member


CurrentMember = Annotated[Member, Depends(get_current_member)]


# ── RBAC — vérification des rôles ─────────────────────────────────────────────

def require_roles(*role_names: RoleName):
    """
    Factory de dépendance — usage :

        @router.get("/admin")
        def admin_route(
            _: Member = Depends(require_roles(RoleName.super_admin, RoleName.treasurer))
        ): ...
    """
    def _check(
        current_member: CurrentMember,
        db: Session = Depends(get_db),
    ) -> Member:
        member_roles = (
            db.query(Role.name)
            .join(MemberRole, MemberRole.role_id == Role.id)
            .filter(MemberRole.member_id == current_member.id)
            .all()
        )
        assigned = {r.name for r in member_roles}
        if not assigned.intersection(set(role_names)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rôle requis : {[r.value for r in role_names]}",
            )
        return current_member

    return _check


# Alias pratiques
RequireAdmin     = Depends(require_roles(RoleName.super_admin))
RequireTreasurer = Depends(require_roles(RoleName.super_admin, RoleName.treasurer))
RequireSecretary = Depends(require_roles(RoleName.super_admin, RoleName.secretary))
