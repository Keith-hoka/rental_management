import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import ComplianceAuditQueue, ComplianceSyncState, LeaseAudit, Notification
from app.services.compliance import drain_audit_queue, poll_audit_changes
from tests.conftest import FAKE_AUDIT
from tests.test_compliance_endpoints import _make_lease
from tests.test_leases import lease_body, make_property
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


def _change(client_ref, new_audit_id, created_at):
    return {
        "id": str(uuid.uuid4()),
        "client_ref": client_ref,
        "old_audit_id": str(uuid.uuid4()),
        "new_audit_id": new_audit_id,
        "changes": {"nsw.bond_max_4_weeks": {"from": "green", "to": "red"}},
        "created_at": created_at,
    }


@pytest.fixture
def fake_feed(monkeypatch):
    """One change for the given client_ref; get_audit returns FAKE_AUDIT with that id."""

    def install(client_ref, new_audit_id=None):
        new_audit_id = new_audit_id or str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        calls = {"count": 0}

        async def _changes(since, limit=100):
            calls["count"] += 1
            if calls["count"] > 1:
                return []
            return [_change(client_ref, new_audit_id, now)]

        async def _get(audit_id):
            body = dict(FAKE_AUDIT)
            body["id"] = audit_id
            body["client_ref"] = client_ref
            return body

        monkeypatch.setattr("app.services.compliance.list_changes", _changes)
        monkeypatch.setattr("app.services.compliance.get_audit", _get)
        return new_audit_id

    return install


async def test_poll_stores_and_notifies_active_lease(client, db_session, compliance_on, fake_feed):
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    new_audit_id = fake_feed(lease["id"])
    count = await poll_audit_changes(db_session)
    assert count == 1
    stored = (await db_session.execute(select(LeaseAudit))).scalar_one()
    assert str(stored.audit_id) == new_audit_id
    notes = (await db_session.execute(select(Notification))).scalars().all()
    assert any(n.category == "compliance" for n in notes)
    cursor = (
        await db_session.execute(
            select(ComplianceSyncState).where(ComplianceSyncState.key == "audit_changes_cursor")
        )
    ).scalar_one()
    assert cursor.value


async def test_poll_skips_superseded_and_unknown(client, db_session, compliance_on, fake_feed):
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    await client.post(
        f"/api/v1/leases/{lease['id']}/renew", json={"end_date": "2027-12-31"}, headers=headers
    )
    fake_feed(lease["id"])
    assert await poll_audit_changes(db_session) == 0
    assert (await db_session.execute(select(LeaseAudit))).first() is None

    fake_feed(str(uuid.uuid4()))
    assert await poll_audit_changes(db_session) == 0


async def test_poll_skips_ended_lease(client, db_session, compliance_on, fake_feed):
    headers = await landlord_headers(client)
    property_id = await make_property(client, headers, "9 Ended St")
    ended = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(start_date="2025-01-01", end_date="2025-12-31"),
            headers=headers,
        )
    ).json()
    fake_feed(ended["id"])
    assert await poll_audit_changes(db_session) == 0
    assert (await db_session.execute(select(LeaseAudit))).first() is None


async def test_poll_rerun_is_idempotent(client, db_session, compliance_on, fake_feed):
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    audit_id = fake_feed(lease["id"])
    await poll_audit_changes(db_session)
    fake_feed(lease["id"], new_audit_id=audit_id)
    assert await poll_audit_changes(db_session) == 0
    assert len((await db_session.execute(select(LeaseAudit))).scalars().all()) == 1
