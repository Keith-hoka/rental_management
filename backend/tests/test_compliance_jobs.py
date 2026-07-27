from sqlalchemy import select

from app.core.config import settings
from app.models import ComplianceAuditQueue, LeaseAudit
from app.services.compliance import drain_audit_queue
from tests.test_compliance_endpoints import _make_lease
from tests.test_properties_crud import landlord_headers


async def test_drain_success_stores_and_deletes(client, db_session, compliance_on, fake_create):
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    count = await drain_audit_queue(db_session)
    assert count == 1
    assert (await db_session.execute(select(ComplianceAuditQueue))).first() is None
    stored = (await db_session.execute(select(LeaseAudit))).scalar_one()
    assert str(stored.lease_id) == lease["id"]


async def test_drain_failure_keeps_row_with_attempts(
    client, db_session, compliance_on, monkeypatch
):
    async def _boom(payload):
        raise RuntimeError("service down")

    monkeypatch.setattr("app.services.compliance.create_audit", _boom)
    headers = await landlord_headers(client)
    await _make_lease(client, headers)
    count = await drain_audit_queue(db_session)
    assert count == 0
    row = (await db_session.execute(select(ComplianceAuditQueue))).scalar_one()
    assert row.attempts == 1
    assert "service down" in row.last_error


async def test_drain_skips_rows_at_max_attempts(client, db_session, compliance_on, fake_create):
    headers = await landlord_headers(client)
    await _make_lease(client, headers)
    row = (await db_session.execute(select(ComplianceAuditQueue))).scalar_one()
    row.attempts = settings.compliance_queue_max_attempts
    await db_session.commit()
    assert await drain_audit_queue(db_session) == 0
    assert (await db_session.execute(select(ComplianceAuditQueue))).first() is not None
