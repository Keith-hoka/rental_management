import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class ComplianceAuditInfo(BaseModel):
    id: uuid.UUID
    audit_id: uuid.UUID
    as_at: date
    findings: list
    jurisdiction: str
    created_at: datetime


class ComplianceAuditState(BaseModel):
    enabled: bool
    audit: ComplianceAuditInfo | None = None
    jurisdiction_status: Literal["ok", "missing", "unsupported"] = "ok"
    jurisdiction: str | None = None
