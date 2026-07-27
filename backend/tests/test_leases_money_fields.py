from sqlalchemy import select

from app.models import ComplianceAuditQueue
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers

MONEY = {
    "rent_in_advance_amount": 1200,
    "holding_deposit_amount": 600,
    "other_security_amount": 0,
    "break_fee_amount": 2400,
}


async def _create_lease(client, headers, **overrides):
    property_id = await make_property(client, headers, "5 Money St")
    response = await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(**overrides),
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_create_persists_and_returns_money_fields(client):
    headers = await landlord_headers(client)
    lease = await _create_lease(client, headers, **MONEY)
    for field, value in MONEY.items():
        assert float(lease[field]) == float(value)


async def test_money_fields_default_to_null(client):
    headers = await landlord_headers(client)
    lease = await _create_lease(client, headers)
    for field in MONEY:
        assert lease[field] is None


async def test_renew_copies_money_fields(client):
    headers = await landlord_headers(client)
    lease = await _create_lease(client, headers, **MONEY)
    renewed = (
        await client.post(
            f"/api/v1/leases/{lease['id']}/renew", json={"end_date": "2027-12-31"}, headers=headers
        )
    ).json()
    for field, value in MONEY.items():
        assert float(renewed[field]) == float(value)


async def test_renew_overrides_money_fields(client):
    headers = await landlord_headers(client)
    lease = await _create_lease(client, headers, **MONEY)
    renewed = (
        await client.post(
            f"/api/v1/leases/{lease['id']}/renew",
            json={"end_date": "2027-12-31", "break_fee_amount": 3000},
            headers=headers,
        )
    ).json()
    assert float(renewed["break_fee_amount"]) == 3000.0
    assert float(renewed["holding_deposit_amount"]) == 600.0


async def test_editing_compliance_field_enqueues(client, db_session, compliance_on):
    headers = await landlord_headers(client)
    lease = await _create_lease(client, headers)
    await db_session.execute(ComplianceAuditQueue.__table__.delete())
    await db_session.commit()
    patched = await client.patch(
        f"/api/v1/leases/{lease['id']}", json={"break_fee_amount": 2500}, headers=headers
    )
    assert patched.status_code == 200
    queued = (await db_session.execute(select(ComplianceAuditQueue))).scalar_one()
    assert str(queued.lease_id) == lease["id"]


async def test_editing_tenant_details_does_not_enqueue(client, db_session, compliance_on):
    headers = await landlord_headers(client)
    lease = await _create_lease(client, headers)
    await db_session.execute(ComplianceAuditQueue.__table__.delete())
    await db_session.commit()
    await client.patch(
        f"/api/v1/leases/{lease['id']}", json={"tenant_name": "Renamed"}, headers=headers
    )
    assert (await db_session.execute(select(ComplianceAuditQueue))).first() is None


async def test_editing_when_disabled_does_not_enqueue(client, db_session):
    headers = await landlord_headers(client)
    lease = await _create_lease(client, headers)
    await client.patch(
        f"/api/v1/leases/{lease['id']}", json={"break_fee_amount": 2500}, headers=headers
    )
    assert (await db_session.execute(select(ComplianceAuditQueue))).first() is None


async def test_unchanged_value_does_not_enqueue(client, db_session, compliance_on):
    headers = await landlord_headers(client)
    lease = await _create_lease(client, headers, **MONEY)
    await db_session.execute(ComplianceAuditQueue.__table__.delete())
    await db_session.commit()
    await client.patch(
        f"/api/v1/leases/{lease['id']}", json={"break_fee_amount": 2400}, headers=headers
    )
    assert (await db_session.execute(select(ComplianceAuditQueue))).first() is None
