"""Client, mapper and jobs for the lease-compliance-service integration."""

import logging
import uuid
from datetime import date
from itertools import pairwise

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import ComplianceAuditQueue, Lease, LeaseAudit

logger = logging.getLogger(__name__)

TIMEOUT = 10.0


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


def chain_to_audit_payload(chain: list[Lease]) -> dict:
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
    if newest.bond_amount is not None:
        lease_body["bond_amount"] = str(newest.bond_amount)
    increases = [
        {"effective_on": later.start_date.isoformat(), "new_amount": str(later.rent_amount)}
        for earlier, later in pairwise(chain)
        if later.rent_amount > earlier.rent_amount
    ]
    if increases:
        lease_body["rent_increases"] = increases
    return {"jurisdiction": "NSW", "client_ref": str(newest.id), "lease": lease_body}


async def run_lease_audit(session: AsyncSession, lease: Lease) -> LeaseAudit:
    """Audit one lease now and store the result. The caller commits."""
    chain = await load_chain(session, lease)
    body = await create_audit(chain_to_audit_payload(chain))
    audit = LeaseAudit(
        lease_id=lease.id,
        organization_id=lease.organization_id,
        audit_id=uuid.UUID(body["id"]),
        as_at=date.fromisoformat(body["as_at"]),
        findings=body["findings"],
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
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the drain
            row.attempts += 1
            row.last_error = str(exc)
            await session.commit()
            continue
        await session.delete(row)
        await session.commit()
        done += 1
    return done
