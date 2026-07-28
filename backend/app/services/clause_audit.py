"""Client and jobs for the compliance service's async clause-audit API."""

import json
import logging
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Document, DocumentVersion, Lease, LeaseClauseAudit

logger = logging.getLogger(__name__)

UPLOAD_TIMEOUT = 30.0
IN_FLIGHT = ("pending", "running")

MONEY_FIELDS = (
    "bond_amount",
    "rent_in_advance_amount",
    "holding_deposit_amount",
    "other_security_amount",
    "break_fee_amount",
)


def _headers() -> dict:
    return {"X-API-Key": settings.compliance_api_key}


async def create_clause_audit(
    filename: str, content: bytes, content_type: str, payload: dict
) -> dict:
    """POST a clause-audit job with the document file and return its body."""
    async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as client:
        response = await client.post(
            f"{settings.compliance_api_url}/v1/clause-audits",
            files={"file": (filename, content, content_type)},
            data={"payload": json.dumps(payload)},
            headers=_headers(),
        )
        response.raise_for_status()
        return response.json()


async def get_clause_audit(job_id: str) -> dict:
    """Fetch one clause-audit job by the service's job id."""
    async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as client:
        response = await client.get(
            f"{settings.compliance_api_url}/v1/clause-audits/{job_id}", headers=_headers()
        )
        response.raise_for_status()
        return response.json()


def lease_fields(lease: Lease) -> dict:
    """The field cross-check subset: money and dates, None omitted."""
    fields = {
        "rent_amount": str(lease.rent_amount),
        "rent_frequency": lease.rent_frequency.value,
        "start_date": lease.start_date.isoformat(),
        "end_date": lease.end_date.isoformat(),
    }
    for name in MONEY_FIELDS:
        value = getattr(lease, name)
        if value is not None:
            fields[name] = str(value)
    return fields


async def latest_version(session: AsyncSession, document_id) -> DocumentVersion | None:
    return (
        await session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def submit_document_audit(
    session: AsyncSession, lease: Lease, document: Document
) -> LeaseClauseAudit:
    """Send the document's latest version for a clause audit. The caller commits."""
    version = await latest_version(session, document.id)
    content = Path(settings.documents_dir, version.stored_name).read_bytes()
    payload = {
        "jurisdiction": "NSW",
        "client_ref": str(lease.id),
        "lease": lease_fields(lease),
    }
    body = await create_clause_audit(
        version.original_filename, content, version.content_type, payload
    )
    row = LeaseClauseAudit(
        organization_id=lease.organization_id,
        lease_id=lease.id,
        document_id=document.id,
        document_version_id=version.id,
        job_id=body["id"],
        status=body["status"],
        model=body["model"],
        engine_version=body["engine_version"],
    )
    session.add(row)
    await session.flush()
    return row
