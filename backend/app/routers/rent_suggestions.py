"""Proxy renewal rent suggestions from the compliance service to a lease."""

import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_ai_consent, require_roles
from app.models import AiFeature, Membership, Property, Role
from app.routers.leases import get_owned_lease
from app.schemas.rent_suggestion import RentSuggestionRequest
from app.services import compliance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["rent-suggestions"])

manager = require_roles(Role.landlord, Role.property_manager)


@router.post("/leases/{lease_id}/rent-suggestion")
async def create_rent_suggestion(
    lease_id: uuid.UUID,
    body: RentSuggestionRequest,
    membership: Membership = Depends(manager),
    _consent: Membership = Depends(require_ai_consent(AiFeature.rent_ai)),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Suggest a renewal rent for the lease, proxied verbatim from the compliance service."""
    if not compliance.enabled():
        raise HTTPException(status_code=503, detail="Compliance integration is not configured")
    lease = await get_owned_lease(lease_id, membership, session)
    try:
        jurisdiction = await compliance.resolve_jurisdiction(session, lease)
    except compliance.JurisdictionUnresolved as exc:
        raise HTTPException(
            status_code=422, detail=f"Property state unresolved: {exc.reason}"
        ) from exc
    property_row = await session.get(Property, lease.property_id)
    chain = await compliance.load_chain(session, lease)
    payload = compliance.rent_suggestion_payload(
        property_row, chain, jurisdiction, body.renewal_start
    )
    try:
        result = await compliance.create_rent_suggestion(payload)
    except httpx.HTTPError as exc:
        logger.warning("Rent suggestion failed for lease %s: %s", lease_id, exc)
        raise HTTPException(status_code=502, detail={"code": "judge_unavailable"}) from exc
    return JSONResponse(content=result)
