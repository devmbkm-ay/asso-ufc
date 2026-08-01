import json
from uuid import UUID, uuid4

from pywebpush import WebPushException, webpush
from sqlalchemy.orm import Session

from app.core.config import settings
from models import MemberNotification, PushSubscription


def notify_member(db: Session, member_id: UUID, type: str, message: str, link: str | None = None) -> None:
    """
    Dépose une notification in-app pour un membre — ne commit pas elle-même,
    s'insère dans la transaction déjà ouverte par l'appelant (même convention
    que _save_notification dans app/api/v1/routes/notifications.py). Envoie
    aussi un vrai push à chaque abonnement enregistré du membre : un même
    évènement métier alimente les deux canaux sans code dupliqué.
    """
    db.add(MemberNotification(
        id=uuid4(),
        member_id=member_id,
        type=type,
        message=message,
        link=link,
    ))
    _send_push(db, member_id, message, link)


def _send_push(db: Session, member_id: UUID, message: str, link: str | None) -> None:
    if not settings.VAPID_PRIVATE_KEY:
        return  # Push non configuré (pas de clés VAPID) — silencieux, l'in-app suffit.

    subscriptions = db.query(PushSubscription).filter(PushSubscription.member_id == member_id).all()
    payload = json.dumps({"title": "Fondation Météo Assistance", "body": message, "link": link})

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_CLAIMS_EMAIL},
            )
        except WebPushException as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code in (404, 410):
                # Abonnement expiré/révoqué côté navigateur — auto-nettoyage.
                db.delete(sub)
            # Toute autre erreur d'envoi ne doit jamais faire échouer l'action
            # métier qui a déclenché la notification : on l'avale ici.
