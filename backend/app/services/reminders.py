from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Lease, LeaseReminder, Property
from app.services.notify import manager_emails, roster_emails, safe_send


def _bucket(days_left: int, thresholds: list[int]) -> int | None:
    """Smallest threshold T with days_left <= T when days_left >= 0, else None."""
    if days_left < 0:
        return None
    for threshold in sorted(thresholds):
        if days_left <= threshold:
            return threshold
    return None


async def _expiring_leases(
    session: AsyncSession, today: date, window_end: date
) -> list[tuple[Lease, str]]:
    """Leases (with property address) whose end_date is in [today, window_end], all orgs."""
    result = await session.execute(
        select(Lease, Property.address)
        .join(Property, Property.id == Lease.property_id)
        .where(Lease.end_date >= today, Lease.end_date <= window_end)
    )
    return list(result.all())


async def _already_sent(session: AsyncSession, lease_id, threshold: int) -> bool:
    result = await session.execute(
        select(LeaseReminder.id).where(
            LeaseReminder.lease_id == lease_id,
            LeaseReminder.threshold_days == threshold,
        )
    )
    return result.first() is not None


async def run_expiry_reminders(session: AsyncSession, today: date) -> int:
    """Email expiry reminders for leases entering a new threshold bucket.

    Returns the number of (lease, bucket) reminders sent this run.
    """
    thresholds = sorted(settings.reminder_thresholds)
    window_end = today + timedelta(days=thresholds[-1])
    sent = 0
    for lease, address in await _expiring_leases(session, today, window_end):
        days_left = (lease.end_date - today).days
        bucket = _bucket(days_left, thresholds)
        if bucket is None or await _already_sent(session, lease.id, bucket):
            continue

        link = f"{settings.frontend_url}/app/leases/{lease.id}"
        manager_subject = f"Lease expiring in {days_left} days - {address}"
        manager_html = (
            f"<p>The lease for {lease.tenant_name} at {address} expires on "
            f"{lease.end_date} ({days_left} days).</p>"
            f'<p><a href="{link}">View the lease</a></p>'
        )
        for email in await manager_emails(session, lease.organization_id):
            await safe_send(email, manager_subject, manager_html)

        tenant_subject = f"Your lease expires in {days_left} days - {address}"
        tenant_html = (
            f"<p>Your lease at {address} expires on {lease.end_date} "
            f"({days_left} days).</p>"
            "<p>Please contact your landlord about renewal.</p>"
            f'<p><a href="{settings.frontend_url}/app">Open your tenant portal</a></p>'
        )
        for email in roster_emails(lease):
            await safe_send(email, tenant_subject, tenant_html)

        session.add(LeaseReminder(lease_id=lease.id, threshold_days=bucket))
        await session.commit()
        sent += 1
    return sent
