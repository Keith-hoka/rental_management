"""Enqueue every active, never-audited lease for a compliance audit.

Usage:
  uv run python -m app.compliance_backfill
  uv run python -m app.compliance_backfill --fix-jurisdictions [--execute]
"""

import argparse
import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.db import SessionLocal
from app.models import AiFeature, Document, Lease, LeaseAudit, LeaseClauseAudit, Property
from app.services import clause_audit
from app.services.ai_consent import feature_enabled
from app.services.compliance import enqueue_audit
from app.services.jurisdiction import jurisdiction_for

logger = logging.getLogger(__name__)


async def backfill(session: AsyncSession) -> dict:
    """Enqueue leases with no audit that are neither ended nor superseded.

    Leases whose property state does not resolve to a supported jurisdiction
    are skipped and counted under "unresolvable_skipped": the drain drops
    them without creating an audit row, so enqueueing them would repeat on
    every run forever.
    """
    successor = aliased(Lease)
    result = await session.execute(
        select(Lease.id, Property.state)
        .join(Property, Property.id == Lease.property_id)
        .where(
            Lease.end_date >= datetime.now(UTC).date(),
            ~select(successor.id).where(successor.renewed_from_id == Lease.id).exists(),
            ~select(LeaseAudit.id).where(LeaseAudit.lease_id == Lease.id).exists(),
        )
    )
    enqueued = 0
    unresolvable = 0
    for lease_id, state in result.all():
        code, _reason = jurisdiction_for(state)
        if code is None:
            unresolvable += 1
            continue
        await enqueue_audit(session, lease_id)
        enqueued += 1
    await session.commit()
    return {"enqueued": enqueued, "unresolvable_skipped": unresolvable}


async def fix_jurisdictions(session: AsyncSession, execute: bool = False) -> dict:
    """Find audits stored under a jurisdiction their property no longer maps to.

    Dry-run by default: reports what would change. With execute=True, enqueues
    deterministic re-audits and resubmits mismatched clause audits, committing
    after each one so a later failure can never undo an earlier success (an
    accepted clause-audit job must not be orphaned by a rollback). A unit that
    raises is logged, rolled back on its own, and its lease id recorded in the
    report's "errors" list instead of aborting the run.

    Counters mean the same thing in both modes: "clause_resubmitted" counts
    documents actually resubmitted (execute) or that would be (dry run), and
    documents that cannot be resubmitted are counted under their skip reason
    instead - so the only dry-run/execute difference is units that fail at
    submit time, which land in "errors". This includes "skipped_no_consent":
    a clause resubmit is an LLM call, so both modes check the organization's
    clause-audit consent before a document counts as resubmittable, and skip
    it without calling out when consent is missing - a dry run's
    "clause_resubmitted" therefore previews exactly what --execute would
    attempt, never more.

    The driving query selects lease ids rather than full Lease rows: a mid-run
    rollback expires every ORM object already loaded in the session, and
    plain attribute access on an expired object raises outside of SQLAlchemy's
    async machinery, so later iterations re-fetch what they need fresh.
    """
    successor = aliased(Lease)
    rows = (
        await session.execute(
            select(Lease.id, Property.state, Lease.organization_id)
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
        "skipped_matching_audits": 0,
        "skipped_matching_clause": 0,
        "skipped_no_version": 0,
        "skipped_in_flight": 0,
        "skipped_no_consent": 0,
        "missing": [],
        "unsupported": [],
        "errors": [],
    }
    for lease_id, state, organization_id in rows:
        code, reason = jurisdiction_for(state)
        if reason == "missing":
            report["missing"].append(lease_id)
            continue
        if reason == "unsupported":
            report["unsupported"].append(lease_id)
            continue
        latest_audit = (
            await session.execute(
                select(LeaseAudit)
                .where(LeaseAudit.lease_id == lease_id)
                .order_by(LeaseAudit.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest_audit is not None and latest_audit.jurisdiction != code:
            if execute:
                try:
                    await enqueue_audit(session, lease_id)
                except Exception as exc:  # noqa: BLE001 - one bad lease must not stop the run
                    logger.warning(
                        "fix_jurisdictions: enqueue failed for lease %s: %s", lease_id, exc
                    )
                    await session.rollback()
                    report["errors"].append(lease_id)
                    continue
                await session.commit()
            report["deterministic_enqueued"] += 1
        elif latest_audit is not None:
            report["skipped_matching_audits"] += 1
        clause_rows = (
            (
                await session.execute(
                    select(LeaseClauseAudit)
                    .where(LeaseClauseAudit.lease_id == lease_id)
                    .order_by(LeaseClauseAudit.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        clause_specs = [(row.document_id, row.jurisdiction) for row in clause_rows]
        seen_documents: set = set()
        for document_id, clause_jurisdiction in clause_specs:
            if document_id in seen_documents:
                continue
            seen_documents.add(document_id)
            if clause_jurisdiction == code:
                report["skipped_matching_clause"] += 1
                continue
            try:
                in_flight = (
                    await session.execute(
                        select(LeaseClauseAudit.id).where(
                            LeaseClauseAudit.document_id == document_id,
                            LeaseClauseAudit.status.in_(clause_audit.IN_FLIGHT),
                        )
                    )
                ).first()
                if in_flight is not None:
                    report["skipped_in_flight"] += 1
                    continue
                version = await clause_audit.latest_version(session, document_id)
                if version is None:
                    report["skipped_no_version"] += 1
                    continue
                if not await feature_enabled(session, organization_id, AiFeature.clause_audit):
                    report["skipped_no_consent"] += 1
                    continue
                if execute:
                    lease = (
                        await session.execute(select(Lease).where(Lease.id == lease_id))
                    ).scalar_one()
                    document = (
                        await session.execute(select(Document).where(Document.id == document_id))
                    ).scalar_one()
                    await clause_audit.submit_document_audit(session, lease, document, version)
                    await session.commit()
                report["clause_resubmitted"] += 1
            except Exception as exc:  # noqa: BLE001 - one bad clause must not stop the run
                logger.warning(
                    "fix_jurisdictions: clause resubmit failed for lease %s document %s: %s",
                    lease_id,
                    document_id,
                    exc,
                )
                await session.rollback()
                report["errors"].append(lease_id)
                continue
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
    args = parser.parse_args(argv)
    if args.execute and not args.fix_jurisdictions:
        parser.error("--execute requires --fix-jurisdictions")
    return args


def _print_report(report: dict) -> None:
    """Print counts as key: value and id lists as one lease id per line."""
    for key, value in report.items():
        if isinstance(value, list):
            print(f"{key} ({len(value)}):")
            for item in value:
                print(f"  {item}")
        else:
            print(f"{key}: {value}")


async def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    async with SessionLocal() as session:
        if args.fix_jurisdictions:
            report = await fix_jurisdictions(session, execute=args.execute)
            _print_report(report)
        else:
            result = await backfill(session)
            print(
                f"backfill: enqueued {result['enqueued']} leases, "
                f"skipped {result['unresolvable_skipped']} unresolvable"
            )


if __name__ == "__main__":
    asyncio.run(main())
