import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import CurrentMember, RequireAdmin
from app.core import email as email_svc
from app.schemas.member import InviteCreate, InviteRead, InviteTokenCheck

from models import Member, MemberInvite

router = APIRouter(prefix="/invites", tags=["Invitations"])


def _invite_to_read(invite: MemberInvite, db: Session) -> InviteRead:
    now = datetime.now(tz=timezone.utc)
    inviter = db.query(Member).filter(Member.id == invite.invited_by).first()
    return InviteRead(
        id=invite.id,
        email=invite.email,
        token=invite.token,
        invited_by_name=f"{inviter.first_name} {inviter.last_name}" if inviter else "—",
        expires_at=invite.expires_at,
        used_at=invite.used_at,
        created_at=invite.created_at,
        is_valid=invite.used_at is None and invite.expires_at > now,
    )


@router.post("", response_model=InviteRead, status_code=status.HTTP_201_CREATED,
             summary="Générer un lien d'invitation")
def create_invite(
    payload: InviteCreate,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireAdmin,
):
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(tz=timezone.utc) + timedelta(days=7)

    invite = MemberInvite(
        id=uuid4(),
        email=str(payload.email),
        token=token,
        invited_by=current_member.id,
        expires_at=expires_at,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    link = f"{settings.FRONTEND_URL}/rejoindre/{token}"
    email_svc.send_invite(invite.email, f"{current_member.first_name} {current_member.last_name}", link)

    return _invite_to_read(invite, db)


@router.get("", response_model=list[InviteRead], summary="Liste des invitations")
def list_invites(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireAdmin,
):
    invites = (
        db.query(MemberInvite)
        .order_by(MemberInvite.created_at.desc())
        .all()
    )
    return [_invite_to_read(inv, db) for inv in invites]


@router.get("/{token}", response_model=InviteTokenCheck, summary="Vérifier un token d'invitation (public)")
def check_invite(token: str, db: Session = Depends(get_db)):
    now = datetime.now(tz=timezone.utc)
    invite = db.query(MemberInvite).filter(MemberInvite.token == token).first()
    if not invite or invite.used_at is not None or invite.expires_at < now:
        raise HTTPException(status_code=400, detail="Lien d'invitation invalide ou expiré")
    return InviteTokenCheck(email=invite.email, valid=True)


@router.delete("/{token}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Révoquer une invitation")
def revoke_invite(
    token: str,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
    _=RequireAdmin,
):
    invite = db.query(MemberInvite).filter(MemberInvite.token == token).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invitation introuvable")
    db.delete(invite)
    db.commit()
