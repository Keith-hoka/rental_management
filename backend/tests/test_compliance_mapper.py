import uuid as uuid_mod
from datetime import date

from sqlalchemy import select

from app.core.config import settings
from app.models import ComplianceAuditQueue, ComplianceSyncState, LeaseAudit
from app.services.compliance import enabled


def test_disabled_by_default():
    assert enabled() is False


def test_enabled_needs_both_values(monkeypatch):
    monkeypatch.setattr(settings, "compliance_api_url", "http://localhost:8100")
    assert enabled() is False
    monkeypatch.setattr(settings, "compliance_api_key", "dev-key")
    assert enabled() is True


async def test_compliance_tables_round_trip(db_session):
    from tests.test_lease_model import make_lease_row

    lease = await make_lease_row(db_session)
    audit = LeaseAudit(
        lease_id=lease.id,
        organization_id=lease.organization_id,
        audit_id=uuid_mod.uuid4(),
        as_at=date(2026, 7, 27),
        findings=[{"rule_id": "nsw.bond_max_4_weeks", "verdict": "green"}],
    )
    queue_row = ComplianceAuditQueue(lease_id=lease.id)
    db_session.add_all([audit, queue_row, ComplianceSyncState(key="cursor", value="x")])
    await db_session.commit()
    stored = (await db_session.execute(select(LeaseAudit))).scalar_one()
    assert stored.findings[0]["verdict"] == "green"
    assert (await db_session.execute(select(ComplianceAuditQueue))).scalar_one().attempts == 0
