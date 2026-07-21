from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Membership
from app.routers.leases import manager
from app.schemas.stats import DashboardStats
from app.services.stats import dashboard_stats

router = APIRouter(prefix="/api/v1", tags=["stats"])


@router.get("/stats", response_model=DashboardStats)
async def get_stats(
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> DashboardStats:
    """Dashboard aggregates for the caller's organization."""
    return await dashboard_stats(session, membership.organization_id, datetime.now(UTC).date())
