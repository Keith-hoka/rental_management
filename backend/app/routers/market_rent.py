"""Proxy the compliance market-rent estimate for a property, with the current-rent gap."""

import logging
import uuid
from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_roles
from app.models import Membership, Role
from app.routers.properties import active_leases_by_property, get_owned_property
from app.services import compliance
from app.services.jurisdiction import property_jurisdiction
from app.services.rent_math import gap_pct, weekly_rent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["market-rent"])

manager = require_roles(Role.landlord, Role.property_manager)


@router.get("/properties/{property_id}/market-rent")
async def get_market_rent(
    property_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """The compliance estimate for the property plus the active lease's weekly rent and gap."""
    if not compliance.enabled():
        raise HTTPException(status_code=503, detail="Compliance integration is not configured")
    prop = await get_owned_property(property_id, membership, session)
    jurisdiction, reason = await property_jurisdiction(session, prop.id)
    if jurisdiction is None:
        raise HTTPException(status_code=422, detail=f"Property state unresolved: {reason}")
    params = compliance.market_rent_params(prop, jurisdiction)
    if not params["area"]:
        raise HTTPException(status_code=422, detail="Property postcode or suburb missing")
    try:
        market = await compliance.get_market_rent(params)
    except httpx.HTTPError as exc:
        logger.warning("Market rent failed for property %s: %s", property_id, exc)
        raise HTTPException(status_code=502, detail={"code": "market_unavailable"}) from exc
    lease = (await active_leases_by_property(session, membership.organization_id, [prop.id])).get(
        prop.id
    )
    current = weekly_rent(Decimal(lease.rent_amount), lease.rent_frequency) if lease else None
    estimate = market.get("estimate_weekly")
    gap = (
        gap_pct(current, Decimal(estimate))
        if current is not None and estimate is not None
        else None
    )
    return JSONResponse(
        content={
            "market": market,
            "current_weekly": None if current is None else str(current),
            "gap_pct": None if gap is None else str(gap),
        }
    )
