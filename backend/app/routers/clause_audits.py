import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_roles
from app.models import Document, DocumentCategory, LeaseClauseAudit, Membership, Role
from app.routers.leases import get_owned_lease
from app.schemas.clause_audit import ClauseAuditInfo, ClauseAuditListState
from app.services import clause_audit, compliance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["clause-audits"])

manager = require_roles(Role.landlord, Role.property_manager)


def _info(row: LeaseClauseAudit) -> ClauseAuditInfo:
    return ClauseAuditInfo(
        id=row.id,
        document_id=row.document_id,
        document_version_id=row.document_version_id,
        job_id=row.job_id,
        status=row.status,
        findings=row.findings,
        discrepancies=row.discrepancies,
        model=row.model,
        engine_version=row.engine_version,
        error=row.error,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


@router.post(
    "/leases/{lease_id}/documents/{document_id}/clause-audit",
    status_code=202,
    response_model=ClauseAuditInfo,
)
async def run_clause_audit(
    lease_id: uuid.UUID,
    document_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> ClauseAuditInfo:
    """Send the document's latest version for an async clause audit."""
    if not compliance.enabled():
        raise HTTPException(status_code=503, detail="Compliance integration is not configured")
    lease = await get_owned_lease(lease_id, membership, session)
    document = (
        await session.execute(
            select(Document).where(Document.id == document_id, Document.lease_id == lease.id)
        )
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.category != DocumentCategory.lease:
        raise HTTPException(status_code=422, detail="Only lease documents can be audited")
    version = await clause_audit.latest_version(session, document.id)
    if version is None:
        raise HTTPException(status_code=404, detail="Document has no versions")
    if version.content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="Only PDF documents can be audited")
    in_flight = (
        await session.execute(
            select(LeaseClauseAudit.id).where(
                LeaseClauseAudit.document_id == document.id,
                LeaseClauseAudit.status.in_(clause_audit.IN_FLIGHT),
            )
        )
    ).first()
    if in_flight is not None:
        raise HTTPException(status_code=409, detail="A clause audit is already in flight")
    try:
        row = await clause_audit.submit_document_audit(session, lease, document, version)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail="The document file is missing from storage; upload a new version",
        ) from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise HTTPException(
                status_code=429, detail="Clause audit queue is full, try again later"
            ) from exc
        if exc.response.status_code == 413:
            raise HTTPException(
                status_code=413, detail="The document exceeds the service's 10 MB limit"
            ) from exc
        logger.warning("Clause audit submit failed for document %s: %s", document_id, exc)
        raise HTTPException(status_code=502, detail="Compliance service unavailable") from exc
    except httpx.HTTPError as exc:
        logger.warning("Clause audit submit failed for document %s: %s", document_id, exc)
        raise HTTPException(status_code=502, detail="Compliance service unavailable") from exc
    await session.commit()
    await session.refresh(row)
    return _info(row)


@router.get("/leases/{lease_id}/clause-audits", response_model=ClauseAuditListState)
async def list_clause_audits(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> ClauseAuditListState:
    """The lease's clause audits, newest first, plus the feature flag."""
    lease = await get_owned_lease(lease_id, membership, session)
    rows = (
        (
            await session.execute(
                select(LeaseClauseAudit)
                .where(LeaseClauseAudit.lease_id == lease.id)
                .order_by(LeaseClauseAudit.created_at.desc(), LeaseClauseAudit.id.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    return ClauseAuditListState(enabled=compliance.enabled(), audits=[_info(row) for row in rows])
