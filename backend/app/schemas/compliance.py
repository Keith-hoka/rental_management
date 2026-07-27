import uuid
from datetime import date, datetime

from pydantic import BaseModel


class ComplianceAuditInfo(BaseModel):
    id: uuid.UUID
    audit_id: uuid.UUID
    as_at: date
    findings: list
    created_at: datetime


class ComplianceAuditState(BaseModel):
    enabled: bool
    audit: ComplianceAuditInfo | None = None
