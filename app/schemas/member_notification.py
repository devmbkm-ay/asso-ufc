from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class MemberNotificationRead(BaseModel):
    id:         UUID
    type:       str
    message:    str
    link:       Optional[str] = None
    read:       bool
    created_at: datetime
