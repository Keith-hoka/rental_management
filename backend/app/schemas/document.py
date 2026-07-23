import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models import DocumentCategory


class DocumentVersionInfo(BaseModel):
    id: uuid.UUID
    version_number: int
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class DocumentInfo(BaseModel):
    id: uuid.UUID
    title: str
    category: DocumentCategory
    version_count: int
    current_version: DocumentVersionInfo
    created_at: datetime
