import secrets
import string
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import CurrentMember, RequirePresidentOrAdmin
from app.schemas.member import JoinCodeRead

from models import JoinCode

router = APIRouter(prefix="/join-code", tags=["Code d'adhésion"])

CODE_ALPHABET = string.ascii_uppercase + string.digits
CODE_LENGTH = 8
CODE_TTL = timedelta(days=30)


def _generate_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def _to_read(code: JoinCode) -> JoinCodeRead:
    return JoinCodeRead(
        code=code.code,
        link=f"{settings.FRONTEND_URL}/rejoindre?code={code.code}",
        is_active=code.is_active,
        expires_at=code.expires_at,
        created_at=code.created_at,
    )


@router.get("", response_model=JoinCodeRead | None,
            summary="Code d'adhésion actif courant")
def get_active_code(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequirePresidentOrAdmin,
):
    now = datetime.now(tz=timezone.utc)
    code = (
        db.query(JoinCode)
        .filter(JoinCode.is_active.is_(True), JoinCode.expires_at > now)
        .order_by(JoinCode.created_at.desc())
        .first()
    )
    return _to_read(code) if code else None


@router.post("", response_model=JoinCodeRead, status_code=status.HTTP_201_CREATED,
             summary="Générer / régénérer le code d'adhésion")
def rotate_code(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequirePresidentOrAdmin,
):
    """Désactive l'éventuel code actif et en crée un nouveau."""
    db.query(JoinCode).filter(JoinCode.is_active.is_(True)).update({"is_active": False})

    code = JoinCode(
        id=uuid4(),
        code=_generate_code(),
        created_by=current_member.id,
        expires_at=datetime.now(tz=timezone.utc) + CODE_TTL,
    )
    db.add(code)
    db.commit()
    db.refresh(code)
    return _to_read(code)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT,
               summary="Désactiver le code d'adhésion actif")
def deactivate_code(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequirePresidentOrAdmin,
):
    db.query(JoinCode).filter(JoinCode.is_active.is_(True)).update({"is_active": False})
    db.commit()


@router.get("/{code}", response_model=dict, summary="Vérifier un code d'adhésion (public)")
def check_code(code: str, db: Session = Depends(get_db)):
    now = datetime.now(tz=timezone.utc)
    join_code = (
        db.query(JoinCode)
        .filter(JoinCode.code == code.upper(), JoinCode.is_active.is_(True), JoinCode.expires_at > now)
        .first()
    )
    if not join_code:
        raise HTTPException(status_code=400, detail="Code d'adhésion invalide ou expiré")
    return {"valid": True}
