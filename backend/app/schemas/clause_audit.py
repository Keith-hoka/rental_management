import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ClauseAuditInfo(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    job_id: str
    status: str
    findings: list
    discrepancies: list
    model: str
    engine_version: str
    jurisdiction: str
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ClauseAuditListState(BaseModel):
    enabled: bool
    audits: list[ClauseAuditInfo] = []
    jurisdiction_status: Literal["ok", "missing", "unsupported"] = "ok"
    jurisdiction: str | None = None
