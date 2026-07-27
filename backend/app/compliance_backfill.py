"""Enqueue every active, never-audited lease for a compliance audit.

Usage: uv run python -m app.compliance_backfill
"""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.db import SessionLocal
from app.models import Lease, LeaseAudit
from app.services.compliance import enqueue_audit


async def backfill(session: AsyncSession) -> int:
    """Enqueue leases with no audit that are neither ended nor superseded."""
    successor = aliased(Lease)
    result = await session.execute(
        select(Lease.id).where(
            Lease.end_date >= datetime.now(UTC).date(),
            ~select(successor.id).where(successor.renewed_from_id == Lease.id).exists(),
            ~select(LeaseAudit.id).where(LeaseAudit.lease_id == Lease.id).exists(),
        )
    )
    count = 0
    for (lease_id,) in result.all():
        await enqueue_audit(session, lease_id)
        count += 1
    await session.commit()
    return count


async def main() -> None:
    async with SessionLocal() as session:
        count = await backfill(session)
    print(f"backfill: enqueued {count} leases")


if __name__ == "__main__":
    asyncio.run(main())
