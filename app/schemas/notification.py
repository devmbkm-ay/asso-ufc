from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class NotificationRead(BaseModel):
    id:        UUID
    member_id: UUID
    type:      str
    subject:   str
    sent:      bool
    sent_at:   Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class ReminderResult(BaseModel):
    total_targeted: int
    sent_count:     int
    failed_count:   int
    skipped_count:  int   # membres sans email ou déjà payé
