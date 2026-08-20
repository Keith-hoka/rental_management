"""Client, mapper and jobs for the lease-compliance-service integration."""

import logging
import uuid
from datetime import UTC, date, datetime
from itertools import pairwise

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    ComplianceAuditQueue,
    ComplianceSyncState,
    Lease,
    LeaseAudit,
    Property,
    PropertyType,
)
from app.services.jurisdiction import JurisdictionUnresolved, property_jurisdiction
from app.services.notify import manager_emails, manager_user_ids, notify_users, safe_send

logger = logging.getLogger(__name__)

TIMEOUT = 10.0
CURSOR_KEY = "audit_changes_cursor"
PAGE_LIMIT = 100


def enabled() -> bool:
    """True when the compliance integration is configured."""
    return bool(settings.compliance_api_url and settings.compliance_api_key)


def _headers() -> dict:
    return {"X-API-Key": settings.compliance_api_key}


async def create_audit(payload: dict) -> dict:
    """POST an audit to the compliance service and return its body."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{settings.compliance_api_url}/v1/audits", json=payload, headers=_headers()
        )
        response.raise_for_status()
        return response.json()


async def create_rent_suggestion(payload: dict) -> dict:
    """POST a renewal rent-suggestion request to the compliance service and return its body."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{settings.compliance_api_url}/v1/rent-suggestions", json=payload, headers=_headers()
        )
        response.raise_for_status()
        return response.json()


async def get_audit(audit_id: str) -> dict:
    """Fetch one audit by the compliance service's audit id."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{settings.compliance_api_url}/v1/audits/{audit_id}", headers=_headers()
        )
        response.raise_for_status()
        return response.json()


async def list_changes(since: str | None, limit: int = 100) -> list[dict]:
    """One page of the tenant's audit-changes feed, ascending."""
    params: dict = {"limit": limit}
    if since is not None:
        params["since"] = since
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{settings.compliance_api_url}/v1/audit-changes",
            params=params,
            headers=_headers(),
        )
        response.raise_for_status()
        return response.json()


async def load_chain(session: AsyncSession, lease: Lease) -> list[Lease]:
    """The renewal chain ending at this lease, oldest first."""
    chain = [lease]
    current = lease
    while current.renewed_from_id is not None:
        current = (
            await session.execute(select(Lease).where(Lease.id == current.renewed_from_id))
        ).scalar_one()
        chain.append(current)
    return list(reversed(chain))


async def resolve_jurisdiction(session: AsyncSession, lease: Lease) -> str:
    """The audit jurisdiction from the lease's property state; raises when unresolved."""
    code, reason = await property_jurisdiction(session, lease.property_id)
    if code is None:
        raise JurisdictionUnresolved(reason)
    return code


def chain_to_audit_payload(chain: list[Lease], jurisdiction: str) -> dict:
    """The compliance audit request for a renewal chain.

    start_date is the tenancy start (chain root): the 12-month first-increase
    rule measures from the tenancy, and successive agreements are continuous.
    An empty synthesis omits rent_increases entirely (None, not []): in-place
    rent edits are invisible here, so an empty list would falsely assert that
    the rent never increased.
    """
    newest = chain[-1]
    lease_body: dict = {
        "rent_amount": str(newest.rent_amount),
        "rent_frequency": newest.rent_frequency.value,
        "start_date": chain[0].start_date.isoformat(),
        "end_date": newest.end_date.isoformat(),
    }
    for field in (
        "bond_amount",
        "rent_in_advance_amount",
        "holding_deposit_amount",
        "other_security_amount",
        "break_fee_amount",
    ):
        value = getattr(newest, field)
        if value is not None:
            lease_body[field] = str(value)
    increases = [
        {"effective_on": later.start_date.isoformat(), "new_amount": str(later.rent_amount)}
        for earlier, later in pairwise(chain)
        if later.rent_amount > earlier.rent_amount
    ]
    if increases:
        lease_body["rent_increases"] = increases
    return {"jurisdiction": jurisdiction, "client_ref": str(newest.id), "lease": lease_body}


_SUGGESTION_DWELLING_TYPES = {"house", "unit", "townhouse", "other"}


def dwelling_type_for(property_type: PropertyType) -> str:
    """The compliance service's dwelling_type for a property type; unmapped types fall back to other."""
    value = property_type.value
    return value if value in _SUGGESTION_DWELLING_TYPES else "other"


def rent_suggestion_payload(
    property_row: Property, chain: list[Lease], jurisdiction: str, renewal_start: date
) -> dict:
    """The compliance rent-suggestion request for a renewal chain.

    area_key is the property's suburb in VIC, where Homes Victoria reports by
    suburb, and its postcode in NSW, where Fair Trading reports by postcode.
    """
    area_key = property_row.city if jurisdiction == "VIC" else property_row.postcode
    return {
        "jurisdiction": jurisdiction,
        "property": {
            "area_key": area_key,
            "dwelling_type": dwelling_type_for(property_row.type),
            "bedrooms": property_row.bedrooms,
        },
        "lease": chain_to_audit_payload(chain, jurisdiction)["lease"],
        "renewal_start": renewal_start.isoformat(),
    }


async def run_lease_audit(session: AsyncSession, lease: Lease) -> LeaseAudit:
    """Audit one lease now and store the result. The caller commits."""
    jurisdiction = await resolve_jurisdiction(session, lease)
    chain = await load_chain(session, lease)
    body = await create_audit(chain_to_audit_payload(chain, jurisdiction))
    audit = LeaseAudit(
        lease_id=lease.id,
        organization_id=lease.organization_id,
        audit_id=uuid.UUID(body["id"]),
        as_at=date.fromisoformat(body["as_at"]),
        findings=body["findings"],
        jurisdiction=jurisdiction,
    )
    session.add(audit)
    await session.flush()
    return audit


async def enqueue_audit(session: AsyncSession, lease_id) -> None:
    """Queue a lease for auditing; a pending duplicate is a no-op."""
    statement = (
        pg_insert(ComplianceAuditQueue)
        .values(lease_id=lease_id)
        .on_conflict_do_nothing(index_elements=["lease_id"])
    )
    await session.execute(statement)


async def drain_audit_queue(session: AsyncSession) -> int:
    """Audit every queued lease; delete rows on success, count attempts on failure."""
    rows = (
        (
            await session.execute(
                select(ComplianceAuditQueue)
                .where(ComplianceAuditQueue.attempts < settings.compliance_queue_max_attempts)
                .order_by(ComplianceAuditQueue.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    done = 0
    for row in rows:
        lease = (await session.execute(select(Lease).where(Lease.id == row.lease_id))).scalar_one()
        try:
            await run_lease_audit(session, lease)
        except JurisdictionUnresolved as exc:
            logger.info(
                "Dropping queued audit for lease %s: jurisdiction %s", row.lease_id, exc.reason
            )
            await session.delete(row)
            await session.commit()
            continue
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the drain
            row.attempts += 1
            row.last_error = str(exc)
            await session.commit()
            continue
        await session.delete(row)
        await session.commit()
        done += 1
    return done


async def _cursor(session: AsyncSession) -> ComplianceSyncState | None:
    return (
        await session.execute(
            select(ComplianceSyncState).where(ComplianceSyncState.key == CURSOR_KEY)
        )
    ).scalar_one_or_none()


def _delta_lines(changes: dict) -> str:
    return "; ".join(f"{rule}: {t['from']} -> {t['to']}" for rule, t in sorted(changes.items()))


async def _lease_for_change(session: AsyncSession, client_ref: str) -> Lease | None:
    """The active lease a change applies to, or None when it should be skipped."""
    try:
        lease_id = uuid.UUID(client_ref)
    except ValueError:
        return None
    lease = (await session.execute(select(Lease).where(Lease.id == lease_id))).scalar_one_or_none()
    if lease is None or lease.end_date < datetime.now(UTC).date():
        return None
    superseded = (
        await session.execute(select(Lease.id).where(Lease.renewed_from_id == lease.id))
    ).first()
    return None if superseded else lease


async def _apply_change(session: AsyncSession, change: dict) -> list[tuple[str, str, str]] | None:
    """Store one change's new audit and queue its notifications; None when skipped.

    Returns the (to, subject, html) emails to send after the caller commits.
    """
    lease = await _lease_for_change(session, change["client_ref"])
    if lease is None:
        logger.info("compliance poll: skipping change for %s", change["client_ref"])
        return None
    audit_id = uuid.UUID(change["new_audit_id"])
    existing = (
        await session.execute(select(LeaseAudit).where(LeaseAudit.audit_id == audit_id))
    ).first()
    if existing is not None:
        return None
    body = await get_audit(change["new_audit_id"])
    session.add(
        LeaseAudit(
            lease_id=lease.id,
            organization_id=lease.organization_id,
            audit_id=audit_id,
            as_at=date.fromisoformat(body["as_at"]),
            findings=body["findings"],
            jurisdiction=body["jurisdiction"],
        )
    )
    delta = _delta_lines(change["changes"])
    body_text = (
        f"The lease for {lease.tenant_name} changed under updated law or rules: "
        f"{delta}. General information, not legal advice."
    )
    await notify_users(
        session,
        await manager_user_ids(session, lease.organization_id),
        lease.organization_id,
        "compliance",
        "Lease compliance status changed",
        body_text,
        f"/app/leases/{lease.id}",
    )
    subject = f"Lease compliance status changed - {lease.tenant_name}"
    html = f"<p>{body_text}</p>"
    return [
        (email, subject, html) for email in await manager_emails(session, lease.organization_id)
    ]


async def poll_audit_changes(session: AsyncSession) -> int:
    """Apply the service's audit-changes feed: store new audits and notify.

    Each change commits (rows plus cursor) before its emails go out, so a
    failure never unsends an email. A failed change stops the run without
    advancing the cursor past it; the next run retries from there.
    """
    state = await _cursor(session)
    applied = 0
    while True:
        since = state.value if state else None
        batch = await list_changes(since, PAGE_LIMIT)
        for change in batch:
            try:
                emails = await _apply_change(session, change)
            except Exception:  # noqa: BLE001 - keep committed changes; retry next run
                logger.exception(
                    "compliance poll: failed on change %s; retrying next run", change["id"]
                )
                await session.rollback()
                return applied
            if state is None:
                state = ComplianceSyncState(key=CURSOR_KEY, value=change["created_at"])
                session.add(state)
            else:
                state.value = change["created_at"]
            await session.commit()
            if emails is not None:
                applied += 1
                for to, subject, html in emails:
                    await safe_send(to, subject, html)
        if len(batch) < PAGE_LIMIT:
            break
    return applied
