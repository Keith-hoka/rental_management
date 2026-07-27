import uuid

from sqlalchemy import select

from app.models import ComplianceAuditQueue, LeaseAudit
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _make_lease(client, headers):
    property_id = await make_property(client, headers, f"{uuid.uuid4().hex[:8]} Compliance St")
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()
    return created


async def test_post_runs_audit_and_stores(client, db_session, compliance_on, fake_create):
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    response = await client.post(f"/api/v1/leases/{lease['id']}/compliance-audit", headers=headers)
    assert response.status_code == 200
    assert response.json()["findings"][0]["verdict"] == "green"
    stored = (await db_session.execute(select(LeaseAudit))).scalar_one()
    assert str(stored.lease_id) == lease["id"]


async def test_post_disabled_is_503(client):
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    response = await client.post(f"/api/v1/leases/{lease['id']}/compliance-audit", headers=headers)
    assert response.status_code == 503


async def test_get_returns_enabled_flag_and_latest(client, compliance_on, fake_create):
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    empty = await client.get(f"/api/v1/leases/{lease['id']}/compliance-audit", headers=headers)
    assert empty.json() == {"enabled": True, "audit": None}
    await client.post(f"/api/v1/leases/{lease['id']}/compliance-audit", headers=headers)
    state = (
        await client.get(f"/api/v1/leases/{lease['id']}/compliance-audit", headers=headers)
    ).json()
    assert state["audit"]["findings"][0]["rule_id"] == "nsw.bond_max_4_weeks"


async def test_create_and_renew_enqueue_when_enabled(client, db_session, compliance_on):
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    queued = (await db_session.execute(select(ComplianceAuditQueue))).scalars().all()
    assert [str(q.lease_id) for q in queued] == [lease["id"]]
    renewed = (
        await client.post(
            f"/api/v1/leases/{lease['id']}/renew", json={"end_date": "2027-12-31"}, headers=headers
        )
    ).json()
    queued = (await db_session.execute(select(ComplianceAuditQueue))).scalars().all()
    assert {str(q.lease_id) for q in queued} == {lease["id"], renewed["id"]}


async def test_create_does_not_enqueue_when_disabled(client, db_session):
    headers = await landlord_headers(client)
    await _make_lease(client, headers)
    assert (await db_session.execute(select(ComplianceAuditQueue))).first() is None


async def test_cross_org_lease_is_404(client, compliance_on, fake_create):
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    outsider = await landlord_headers(client, email="other-org@example.com")
    response = await client.post(f"/api/v1/leases/{lease['id']}/compliance-audit", headers=outsider)
    assert response.status_code == 404


async def test_delete_audited_lease_cascades(client, db_session, compliance_on, fake_create):
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    await client.post(f"/api/v1/leases/{lease['id']}/compliance-audit", headers=headers)
    deleted = await client.delete(f"/api/v1/leases/{lease['id']}", headers=headers)
    assert deleted.status_code == 204
    assert (await db_session.execute(select(LeaseAudit))).first() is None
    assert (await db_session.execute(select(ComplianceAuditQueue))).first() is None
