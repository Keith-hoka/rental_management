import uuid as uuid_mod
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.core.config import settings
from app.models import ComplianceAuditQueue, ComplianceSyncState, Lease, LeaseAudit, LeaseFrequency
from app.services.compliance import chain_to_audit_payload, enabled, load_chain


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


def _lease(start, end, rent, bond=None, prev=None):
    lease = Lease(
        id=uuid_mod.uuid4(),
        organization_id=uuid_mod.uuid4(),
        property_id=uuid_mod.uuid4(),
        tenant_name="T",
        tenant_email="t@example.com",
        co_tenants=[],
        rent_amount=Decimal(rent),
        rent_frequency=LeaseFrequency.weekly,
        bond_amount=Decimal(bond) if bond is not None else None,
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        renewed_from_id=prev.id if prev is not None else None,
    )
    return lease


def test_payload_single_lease_no_increases():
    lease = _lease("2026-01-01", "2026-12-31", 600, bond=2400)
    payload = chain_to_audit_payload([lease])
    assert payload["jurisdiction"] == "NSW"
    assert payload["client_ref"] == str(lease.id)
    body = payload["lease"]
    assert body["start_date"] == "2026-01-01"
    assert body["end_date"] == "2026-12-31"
    assert body["rent_amount"] == "600"
    assert body["rent_frequency"] == "weekly"
    assert body["bond_amount"] == "2400"
    assert "rent_increases" not in body


def test_payload_chain_synthesises_increases_from_root():
    first = _lease("2024-01-01", "2024-12-31", 600)
    second = _lease("2025-01-01", "2025-12-31", 650, prev=first)
    third = _lease("2026-01-01", "2026-12-31", 650, prev=second)
    payload = chain_to_audit_payload([first, second, third])
    body = payload["lease"]
    assert payload["client_ref"] == str(third.id)
    assert body["start_date"] == "2024-01-01"
    assert body["end_date"] == "2026-12-31"
    assert body["rent_increases"] == [{"effective_on": "2025-01-01", "new_amount": "650"}]


def test_payload_decrease_emits_nothing():
    first = _lease("2024-01-01", "2024-12-31", 700)
    second = _lease("2025-01-01", "2025-12-31", 650, prev=first)
    payload = chain_to_audit_payload([first, second])
    assert "rent_increases" not in payload["lease"]


def test_payload_omits_missing_bond():
    lease = _lease("2026-01-01", "2026-12-31", 600)
    assert "bond_amount" not in chain_to_audit_payload([lease])["lease"]


async def test_load_chain_walks_to_root(db_session):
    from tests.test_lease_model import make_lease_row

    root = await make_lease_row(db_session)
    middle = await make_lease_row(db_session, renewed_from_id=root.id)
    newest = await make_lease_row(db_session, renewed_from_id=middle.id)
    await db_session.commit()
    chain = await load_chain(db_session, newest)
    assert [lease.id for lease in chain] == [root.id, middle.id, newest.id]
