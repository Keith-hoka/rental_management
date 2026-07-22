from collections import defaultdict
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Lease,
    MaintenanceRequest,
    MaintenanceStatus,
    Membership,
    Payment,
    Property,
    Role,
)
from app.schemas.stats import DashboardStats, MonthlyIncome
from app.services.payments import lease_balance


async def _count(session: AsyncSession, stmt) -> int:
    return (await session.execute(stmt)).scalar_one()


async def _collected_since(session: AsyncSession, organization_id, since: date) -> Decimal:
    result = await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.organization_id == organization_id, Payment.paid_on >= since
        )
    )
    return Decimal(result.scalar_one())


async def _monthly_income(
    session: AsyncSession, organization_id, today: date
) -> list[MonthlyIncome]:
    months = [today.replace(day=1) - relativedelta(months=i) for i in range(5, -1, -1)]
    result = await session.execute(
        select(Payment.paid_on, Payment.amount).where(
            Payment.organization_id == organization_id, Payment.paid_on >= months[0]
        )
    )
    buckets: dict[tuple[int, int], Decimal] = defaultdict(lambda: Decimal("0"))
    for paid_on, amount in result.all():
        buckets[(paid_on.year, paid_on.month)] += amount
    return [
        MonthlyIncome(month=f"{d.year:04d}-{d.month:02d}", amount=buckets[(d.year, d.month)])
        for d in months
    ]


async def dashboard_stats(session: AsyncSession, organization_id, today: date) -> DashboardStats:
    """Aggregate the organization's money and portfolio figures for the dashboard."""
    leases = (
        (await session.execute(select(Lease).where(Lease.organization_id == organization_id)))
        .scalars()
        .all()
    )
    outstanding = Decimal("0")
    overdue = Decimal("0")
    for lease in leases:
        balance = await lease_balance(session, lease.id, today)
        outstanding += balance.outstanding
        overdue += balance.overdue_amount

    active = [lease for lease in leases if lease.start_date <= today <= lease.end_date]
    properties_total = await _count(
        session,
        select(func.count())
        .select_from(Property)
        .where(Property.organization_id == organization_id),
    )
    tenants = await _count(
        session,
        select(func.count())
        .select_from(Membership)
        .where(Membership.organization_id == organization_id, Membership.role == Role.tenant),
    )
    maintenance_open = await _count(
        session,
        select(func.count())
        .select_from(MaintenanceRequest)
        .where(
            MaintenanceRequest.organization_id == organization_id,
            MaintenanceRequest.status.in_([MaintenanceStatus.open, MaintenanceStatus.in_progress]),
        ),
    )
    return DashboardStats(
        outstanding=outstanding,
        overdue=overdue,
        collected_this_month=await _collected_since(session, organization_id, today.replace(day=1)),
        properties_total=properties_total,
        properties_occupied=len({lease.property_id for lease in active}),
        active_leases=len(active),
        tenants=tenants,
        maintenance_open=maintenance_open,
        monthly_income=await _monthly_income(session, organization_id, today),
    )
