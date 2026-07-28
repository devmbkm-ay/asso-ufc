from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class DeathReportCreate(BaseModel):
    member_id:      Optional[UUID] = None  # sens A : signalement du décès d'un membre
    designation_id: Optional[UUID] = None  # sens B : signalement du décès d'une personne désignée
    note:           Optional[str] = Field(None, max_length=1000)

    @model_validator(mode="after")
    def _exactly_one_target(self):
        if bool(self.member_id) == bool(self.designation_id):
            raise ValueError("Préciser soit member_id soit designation_id, jamais les deux ni aucun")
        return self


class DeathReportRead(BaseModel):
    id:             UUID
    member_id:      Optional[UUID]
    designation_id: Optional[UUID]
    target_label:   str
    reported_by:    UUID
    reporter_name:  str
    note:           Optional[str]
    status:         str
    reviewed_by:    Optional[UUID] = None
    reviewed_at:    Optional[datetime] = None
    created_at:     datetime