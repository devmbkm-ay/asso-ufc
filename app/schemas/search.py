from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class SearchResultItem(BaseModel):
    type: Literal["member", "event", "collecte"]
    id: UUID
    title: str
    subtitle: str | None = None
    href: str
