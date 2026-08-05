"""Enqueue every active, never-audited lease for a compliance audit.

Usage:
  uv run python -m app.compliance_backfill
  uv run python -m app.compliance_backfill --fix-jurisdictions [--execute]
"""

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.db import SessionLocal
from app.models import Document, Lease, LeaseAudit, LeaseClauseAudit, Property
from app.services import clause_audit
from app.services.compliance import enqueue_audit
from app.services.jurisdiction import jurisdiction_for


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


async def fix_jurisdictions(session: AsyncSession, execute: bool = False) -> dict:
    """Find audits stored under a jurisdiction their property no longer maps to.

    Dry-run by default: reports what would change; execute=True enqueues
    deterministic re-audits and resubmits mismatched clause audits.
    """
    successor = aliased(Lease)
    rows = (
        await session.execute(
            select(Lease, Property.state)
            .join(Property, Property.id == Lease.property_id)
            .where(
                Lease.end_date >= datetime.now(UTC).date(),
                ~select(successor.id).where(successor.renewed_from_id == Lease.id).exists(),
            )
        )
    ).all()
    report: dict = {
        "deterministic_enqueued": 0,
        "clause_resubmitted": 0,
        "skipped_matching": 0,
        "missing": [],
        "unsupported": [],
    }
    for lease, state in rows:
        code, reason = jurisdiction_for(state)
        if reason == "missing":
            report["missing"].append(lease.id)
            continue
        if reason == "unsupported":
            report["unsupported"].append(lease.id)
            continue
        latest_audit = (
            await session.execute(
                select(LeaseAudit)
                .where(LeaseAudit.lease_id == lease.id)
                .order_by(LeaseAudit.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest_audit is not None and latest_audit.jurisdiction != code:
            if execute:
                await enqueue_audit(session, lease.id)
            report["deterministic_enqueued"] += 1
        elif latest_audit is not None:
            report["skipped_matching"] += 1
        clause_rows = (
            (
                await session.execute(
                    select(LeaseClauseAudit)
                    .where(LeaseClauseAudit.lease_id == lease.id)
                    .order_by(LeaseClauseAudit.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        seen_documents: set = set()
        for clause_row in clause_rows:
            if clause_row.document_id in seen_documents:
                continue
            seen_documents.add(clause_row.document_id)
            if clause_row.jurisdiction == code:
                report["skipped_matching"] += 1
                continue
            if execute:
                document = (
                    await session.execute(
                        select(Document).where(Document.id == clause_row.document_id)
                    )
                ).scalar_one()
                version = await clause_audit.latest_version(session, document.id)
                if version is not None:
                    await clause_audit.submit_document_audit(session, lease, document, version)
            report["clause_resubmitted"] += 1
    if execute:
        await session.commit()
    return report


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compliance backfill jobs.")
    parser.add_argument(
        "--fix-jurisdictions",
        action="store_true",
        help="Report leases and clause audits stored under a stale jurisdiction",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform the fix instead of a dry run (only with --fix-jurisdictions)",
    )
    return parser.parse_args(argv)


def _print_report(report: dict) -> None:
    for key, value in report.items():
        print(f"{key}: {value}")


async def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    async with SessionLocal() as session:
        if args.fix_jurisdictions:
            report = await fix_jurisdictions(session, execute=args.execute)
            _print_report(report)
        else:
            count = await backfill(session)
            print(f"backfill: enqueued {count} leases")


if __name__ == "__main__":
    asyncio.run(main())
