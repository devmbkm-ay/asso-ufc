from pydantic import BaseModel


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionCreate(BaseModel):
    """Reprend exactement la forme de PushSubscription.toJSON() côté navigateur."""
    endpoint: str
    keys: PushSubscriptionKeys


class PushSubscriptionDelete(BaseModel):
    endpoint: str


class VapidPublicKey(BaseModel):
    public_key: str
