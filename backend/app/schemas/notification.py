import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationInfo(BaseModel):
    id: uuid.UUID
    category: str
    title: str
    body: str
    link: str | None
    created_at: datetime
    read_at: datetime | None


class UnreadCount(BaseModel):
    count: int
