from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Charge, ChargeReminder, Lease, Property
from app.services.notify import (
    lease_tenant_user_ids,
    manager_emails,
    manager_user_ids,
    notify_users,
    roster_emails,
    safe_send,
)
from app.services.payments import ChargeStatus, lease_statuses

DUE_SOON = "due_soon"
DUE_SOON_LEAD = 3
OVERDUE_THRESHOLDS = [7, 14, 30]


def _due_soon(days_until: int) -> bool:
    """True from DUE_SOON_LEAD days before the due date through the due date itself."""
    return 0 <= days_until <= DUE_SOON_LEAD


def _overdue_kind(days_overdue: int) -> str | None:
    """The largest overdue threshold reached, or None below the first one.

    Largest-reached rather than smallest-crossed keeps the job self-healing: after a
    missed run, a charge 16 days overdue still gets overdue_14 instead of stalling.
    """
    reached = [t for t in OVERDUE_THRESHOLDS if t <= days_overdue]
    return f"overdue_{max(reached)}" if reached else None


def _kind(due_date: date, today: date) -> str | None:
    """The reminder kind a charge qualifies for today, if any."""
    days_until = (due_date - today).days
    if days_until >= 0:
        return DUE_SOON if _due_soon(days_until) else None
    return _overdue_kind(-days_until)


@dataclass
class _Copy:
    subject: str
    html: str
    category: str
    title: str
    body: str


def _copy_for(
    kind: str, address: str, charge: Charge, owed: Decimal, url: str, today: date
) -> _Copy:
    """The email and in-app wording for one reminder kind."""
    if kind == DUE_SOON:
        return _Copy(
            subject=f"Rent due {charge.due_date} - {address}",
            html=(
                f"<p>Rent of ${owed} for {address} is due on {charge.due_date}.</p>"
                f'<p><a href="{url}">View your lease</a></p>'
            ),
            category="rent_due",
            title=f"Rent due {charge.due_date}",
            body=f"${owed} for {address} is due on {charge.due_date}.",
        )
    days = (today - charge.due_date).days
    return _Copy(
        subject=f"Rent overdue by {days} days - {address}",
        html=(
            f"<p>Rent of ${owed} for {address} was due on {charge.due_date} "
            f"({days} days ago).</p>"
            f'<p><a href="{url}">View the lease</a></p>'
        ),
        category="rent_overdue",
        title=f"Rent overdue by {days} days",
        body=f"${owed} for {address} was due on {charge.due_date}.",
    )


async def _leases_with_due_charges(session: AsyncSession, today: date) -> list[tuple[Lease, str]]:
    """Leases (with property address) holding a charge due on or before the lead horizon."""
    horizon = today + timedelta(days=DUE_SOON_LEAD)
    result = await session.execute(
        select(Lease, Property.address)
        .join(Property, Property.id == Lease.property_id)
        .where(Lease.id.in_(select(Charge.lease_id).where(Charge.due_date <= horizon)))
    )
    return list(result.all())


async def _already_sent(session: AsyncSession, charge_id, kind: str) -> bool:
    result = await session.execute(
        select(ChargeReminder.id).where(
            ChargeReminder.charge_id == charge_id, ChargeReminder.kind == kind
        )
    )
    return result.first() is not None


async def _send(
    session: AsyncSession,
    lease: Lease,
    address: str,
    status: ChargeStatus,
    kind: str,
    today: date,
) -> None:
    """Email the recipients for this kind and post the matching in-app notifications."""
    charge = status.charge
    owed = charge.amount_due - status.amount_paid
    link = f"/app/leases/{lease.id}"
    copy = _copy_for(kind, address, charge, owed, f"{settings.frontend_url}{link}", today)

    emails = roster_emails(lease)
    user_ids = await lease_tenant_user_ids(session, lease.id)
    if kind != DUE_SOON:
        emails += await manager_emails(session, lease.organization_id)
        user_ids += await manager_user_ids(session, lease.organization_id)

    for email in emails:
        await safe_send(email, copy.subject, copy.html)
    await notify_users(
        session, user_ids, lease.organization_id, copy.category, copy.title, copy.body, link
    )


async def run_rent_reminders(session: AsyncSession, today: date) -> int:
    """Remind tenants of rent due soon, and tenants plus managers of overdue rent.

    Returns the number of (charge, kind) reminders sent this run.
    """
    sent = 0
    for lease, address in await _leases_with_due_charges(session, today):
        for status in await lease_statuses(session, lease.id, today):
            kind = _kind(status.charge.due_date, today)
            if kind is None or status.status == "paid":
                continue
            if await _already_sent(session, status.charge.id, kind):
                continue

            await _send(session, lease, address, status, kind, today)
            session.add(ChargeReminder(charge_id=status.charge.id, kind=kind))
            await session.commit()
            sent += 1
    return sent
