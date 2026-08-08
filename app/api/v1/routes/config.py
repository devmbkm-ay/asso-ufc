from fastapi import APIRouter

from app.core.config import settings
from app.core.deps import CurrentMember
from app.schemas.config import PaymentInfo

router = APIRouter(prefix="/config", tags=["Configuration"])


@router.get("/payment-info", response_model=PaymentInfo,
            summary="Infos non sensibles pour afficher les moyens de paiement (ex: destinataire PayPal)")
def get_payment_info(current_member: CurrentMember):
    return PaymentInfo(paypal_recipient=settings.PAYPAL_RECIPIENT or None)
