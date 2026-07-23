from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Membership
from app.routers.leases import manager
from app.schemas.report import MonthlyReport
from app.services.reports import monthly_report

router = APIRouter(prefix="/api/v1", tags=["reports"])


@router.get("/reports/monthly", response_model=MonthlyReport)
async def monthly(
    months: int = 12,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> MonthlyReport:
    """A months-long accrual P&L series, expenses by category, and per-property P&L."""
    months = max(1, min(months, 24))
    return await monthly_report(session, membership.organization_id, months)
