from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from models import MemberNotification


def notify_member(db: Session, member_id: UUID, type: str, message: str, link: str | None = None) -> None:
    """
    Dépose une notification in-app pour un membre — ne commit pas elle-même,
    s'insère dans la transaction déjà ouverte par l'appelant (même convention
    que _save_notification dans app/api/v1/routes/notifications.py).
    """
    db.add(MemberNotification(
        id=uuid4(),
        member_id=member_id,
        type=type,
        message=message,
        link=link,
    ))
