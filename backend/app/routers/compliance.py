import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_roles
from app.models import LeaseAudit, Membership, Property, Role
from app.routers.leases import get_owned_lease
from app.schemas.compliance import ComplianceAuditInfo, ComplianceAuditState
from app.services import compliance
from app.services.jurisdiction import jurisdiction_for

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["compliance"])

manager = require_roles(Role.landlord, Role.property_manager)


def _info(audit: LeaseAudit) -> ComplianceAuditInfo:
    return ComplianceAuditInfo(
        id=audit.id,
        audit_id=audit.audit_id,
        as_at=audit.as_at,
        findings=audit.findings,
        jurisdiction=audit.jurisdiction,
        created_at=audit.created_at,
    )


@router.post("/leases/{lease_id}/compliance-audit", response_model=ComplianceAuditInfo)
async def run_audit_now(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> ComplianceAuditInfo:
    """Audit the lease synchronously and store the result."""
    if not compliance.enabled():
        raise HTTPException(status_code=503, detail="Compliance integration is not configured")
    lease = await get_owned_lease(lease_id, membership, session)
    try:
        audit = await compliance.run_lease_audit(session, lease)
    except compliance.JurisdictionUnresolved as exc:
        raise HTTPException(
            status_code=422, detail=f"Property state unresolved: {exc.reason}"
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("Compliance audit failed for lease %s: %s", lease_id, exc)
        raise HTTPException(status_code=502, detail="Compliance service unavailable") from exc
    await session.commit()
    return _info(audit)


@router.get("/leases/{lease_id}/compliance-audit", response_model=ComplianceAuditState)
async def latest_audit(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> ComplianceAuditState:
    """The newest stored audit for the lease, plus the feature flag and live jurisdiction status."""
    lease = await get_owned_lease(lease_id, membership, session)
    row = (
        await session.execute(
            select(LeaseAudit)
            .where(LeaseAudit.lease_id == lease.id)
            .order_by(LeaseAudit.created_at.desc(), LeaseAudit.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    state_value = (
        await session.execute(select(Property.state).where(Property.id == lease.property_id))
    ).scalar_one()
    code, reason = jurisdiction_for(state_value)
    return ComplianceAuditState(
        enabled=compliance.enabled(),
        audit=_info(row) if row is not None else None,
        jurisdiction_status=reason,
        jurisdiction=code,
    )
