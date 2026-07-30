from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.database import get_db
from app.core.deps import CurrentMember
from app.schemas.member_notification import MemberNotificationRead
from models import MemberNotification

router = APIRouter(prefix="/notifications/me", tags=["Mes notifications"])


@router.get("", response_model=list[MemberNotificationRead],
            summary="Mes notifications")
def list_my_notifications(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    rows = (
        db.query(MemberNotification)
        .filter(MemberNotification.member_id == current_member.id)
        .order_by(MemberNotification.created_at.desc())
        .all()
    )
    return rows


@router.patch("/{notification_id}/read", response_model=MemberNotificationRead,
              summary="Marquer une notification comme lue")
def mark_notification_read(
    notification_id: UUID,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    n = db.query(MemberNotification).filter(
        MemberNotification.id == notification_id,
        MemberNotification.member_id == current_member.id,
    ).first()
    if not n:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification introuvable")
    n.read = True
    db.commit()
    db.refresh(n)
    return n


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT,
             summary="Marquer toutes mes notifications comme lues")
def mark_all_notifications_read(
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    db.query(MemberNotification).filter(
        MemberNotification.member_id == current_member.id,
        MemberNotification.read == False,  # noqa: E712
    ).update({"read": True})
    db.commit()
