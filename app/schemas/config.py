from pydantic import BaseModel


class PaymentInfo(BaseModel):
    paypal_recipient: str | None = None
