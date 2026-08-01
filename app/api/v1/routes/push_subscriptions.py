from uuid import uuid4

from fastapi import APIRouter, Depends, status
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import CurrentMember
from app.schemas.push import PushSubscriptionCreate, PushSubscriptionDelete, VapidPublicKey
from models import PushSubscription

router = APIRouter(prefix="/push", tags=["Notifications push"])


@router.get("/vapid-public-key", response_model=VapidPublicKey,
            summary="Clé publique VAPID à utiliser pour l'abonnement push")
def get_vapid_public_key(current_member: CurrentMember):
    return VapidPublicKey(public_key=settings.VAPID_PUBLIC_KEY)


@router.post("/subscriptions", status_code=status.HTTP_204_NO_CONTENT,
             summary="Enregistrer un abonnement push")
def create_subscription(
    payload: PushSubscriptionCreate,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    """
    Upsert sur `endpoint` : si ce navigateur était déjà abonné (même sous un
    autre membre, ex. appareil partagé), on réattribue l'abonnement plutôt
    que d'échouer sur la contrainte d'unicité.
    """
    stmt = pg_insert(PushSubscription).values(
        id=uuid4(),
        member_id=current_member.id,
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
    ).on_conflict_do_update(
        index_elements=["endpoint"],
        set_={"member_id": current_member.id, "p256dh": payload.keys.p256dh, "auth": payload.keys.auth},
    )
    db.execute(stmt)
    db.commit()


@router.delete("/subscriptions", status_code=status.HTTP_204_NO_CONTENT,
                summary="Retirer un abonnement push")
def delete_subscription(
    payload: PushSubscriptionDelete,
    current_member: CurrentMember,
    db: Session = Depends(get_db),
):
    db.query(PushSubscription).filter(
        PushSubscription.endpoint == payload.endpoint,
        PushSubscription.member_id == current_member.id,
    ).delete()
    db.commit()
