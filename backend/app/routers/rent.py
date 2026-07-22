import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Lease, Membership, Property
from app.routers.leases import manager
from app.schemas.charge import ChargeInfo
from app.schemas.rent import LeaseChargeGroup, RentSummary
from app.services.payments import ChargeStatus, org_charge_statuses

router = APIRouter(prefix="/api/v1", tags=["rent"])


def _to_charge_info(status: ChargeStatus) -> ChargeInfo:
    return ChargeInfo(
        id=status.charge.id,
        period_start=status.charge.period_start,
        period_end=status.charge.period_end,
        due_date=status.charge.due_date,
        amount_due=status.charge.amount_due,
        amount_paid=status.amount_paid,
        status=status.status,
        overdue=status.overdue,
    )


def _group(
    lease_id: uuid.UUID,
    address: str,
    tenant_name: str,
    statuses: list[ChargeStatus],
) -> LeaseChargeGroup | None:
    """One bucket row, or None when nothing in it is still owed.

    The filter applies to both buckets: a tenant who pays ahead leaves a future
    charge with nothing owing, and it drops out of upcoming exactly as a settled
    charge drops out of overdue.
    """
    owing = [s for s in statuses if s.charge.amount_due > s.amount_paid]
    if not owing:
        return None
    return LeaseChargeGroup(
        lease_id=lease_id,
        property_address=address,
        tenant_name=tenant_name,
        total=sum((s.charge.amount_due - s.amount_paid for s in owing), Decimal("0")),
        oldest_due=min(s.charge.due_date for s in owing),
        charges=[_to_charge_info(s) for s in owing],
    )


def _past(statuses: list[ChargeStatus], today: date) -> list[ChargeStatus]:
    return [s for s in statuses if s.charge.due_date < today]


def _future(statuses: list[ChargeStatus], today: date) -> list[ChargeStatus]:
    return [s for s in statuses if s.charge.due_date >= today]


def _append(target: list[LeaseChargeGroup], group: LeaseChargeGroup | None) -> None:
    if group is not None:
        target.append(group)


@router.get("/rent/summary", response_model=RentSummary)
async def rent_summary(
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> RentSummary:
    """Unsettled rent for the organization, split into overdue and upcoming."""
    today = datetime.now(UTC).date()
    by_lease = await org_charge_statuses(session, membership.organization_id, today)
    rows = (
        await session.execute(
            select(Lease.id, Lease.tenant_name, Property.address)
            .join(Property, Property.id == Lease.property_id)
            .where(Lease.organization_id == membership.organization_id)
        )
    ).all()

    overdue: list[LeaseChargeGroup] = []
    upcoming: list[LeaseChargeGroup] = []
    for lease_id, tenant_name, address in rows:
        statuses = by_lease.get(lease_id, [])
        _append(overdue, _group(lease_id, address, tenant_name, _past(statuses, today)))
        _append(upcoming, _group(lease_id, address, tenant_name, _future(statuses, today)))

    overdue.sort(key=lambda g: g.oldest_due)
    upcoming.sort(key=lambda g: g.oldest_due)
    return RentSummary(overdue=overdue, upcoming=upcoming)
