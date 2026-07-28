"""Client and jobs for the compliance service's async clause-audit API."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Document, DocumentVersion, Lease, LeaseClauseAudit
from app.services.notify import manager_emails, manager_user_ids, notify_users, safe_send

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


def _summary(row: LeaseClauseAudit) -> str:
    if row.status == "failed":
        return "Clause audit failed"
    reds = sum(1 for f in row.findings if f["verdict"] == "red")
    yellows = sum(1 for f in row.findings if f["verdict"] == "yellow")
    mismatches = len(row.discrepancies)
    if not (reds or yellows or mismatches):
        return "Clause audit finished: all green"
    return f"Clause audit finished: {reds} red, {yellows} yellow, {mismatches} field mismatch"


async def _notify_completion(session: AsyncSession, row: LeaseClauseAudit) -> list[tuple]:
    """Queue in-app notifications; return (to, subject, html) emails for after commit."""
    lease = (await session.execute(select(Lease).where(Lease.id == row.lease_id))).scalar_one()
    document = (
        await session.execute(select(Document).where(Document.id == row.document_id))
    ).scalar_one()
    summary = _summary(row)
    title = "Clause audit failed" if row.status == "failed" else "Clause audit finished"
    body_text = f"{document.title}: {summary}. General information, not legal advice."
    await notify_users(
        session,
        await manager_user_ids(session, row.organization_id),
        row.organization_id,
        "compliance",
        title,
        body_text,
        f"/app/leases/{lease.id}",
    )
    subject = f"{title} - {lease.tenant_name}"
    html = f"<p>{body_text}</p>"
    return [(email, subject, html) for email in await manager_emails(session, row.organization_id)]


async def poll_clause_audits(session: AsyncSession) -> int:
    """Advance every in-flight clause audit; one bad row never blocks the rest.

    Rows reload by id each iteration: a rollback expires every loaded
    instance, so carrying ORM objects across iterations would blow up on
    attribute access after one bad row.
    """
    row_ids = (
        (
            await session.execute(
                select(LeaseClauseAudit.id)
                .where(LeaseClauseAudit.status.in_(IN_FLIGHT))
                .order_by(LeaseClauseAudit.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    updated = 0
    for row_id in row_ids:
        try:
            row = await session.get(LeaseClauseAudit, row_id)
            body = await get_clause_audit(row.job_id)
            if body["status"] not in ("succeeded", "failed"):
                if body["status"] != row.status:
                    row.status = body["status"]
                    await session.commit()
                continue
            row.status = body["status"]
            row.findings = body["findings"]
            row.discrepancies = body["discrepancies"]
            row.error = body["error"]
            row.completed_at = datetime.now(UTC)
            emails = await _notify_completion(session, row)
            await session.commit()
            updated += 1
            for to, subject, html in emails:
                await safe_send(to, subject, html)
        except Exception:  # noqa: BLE001 - keep polling the other rows
            logger.exception("clause audit poll: failed on row %s", row_id)
            await session.rollback()
            continue
    return updated
