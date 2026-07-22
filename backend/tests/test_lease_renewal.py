import uuid

from sqlalchemy import select

from app.models import Lease
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def test_renewed_from_id_defaults_to_none(client, db_session):
    headers = await landlord_headers(client)
    property_id = await make_property(client, headers)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()
    lease = (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(created["id"])))
    ).scalar_one()
    assert lease.renewed_from_id is None


async def _make_lease(client, headers, **overrides):
    property_id = await make_property(client, headers, overrides.pop("address", "1 Renew St"))
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(**overrides),
            headers=headers,
        )
    ).json()
    return property_id, created


async def test_renew_copies_tenant_and_defaults_start_to_day_after(client):
    headers = await landlord_headers(client)
    _, lease = await _make_lease(client, headers)
    response = await client.post(
        f"/api/v1/leases/{lease['id']}/renew",
        json={"end_date": "2027-12-31"},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["tenant_name"] == lease["tenant_name"]
    assert body["tenant_email"] == lease["tenant_email"]
    assert body["start_date"] == "2027-01-01"
    assert body["end_date"] == "2027-12-31"
    assert float(body["rent_amount"]) == float(lease["rent_amount"])
    assert body["rent_frequency"] == lease["rent_frequency"]
    assert body["renewed_from_id"] == lease["id"]
    assert body["id"] != lease["id"]


async def test_renew_applies_overrides(client):
    headers = await landlord_headers(client)
    _, lease = await _make_lease(client, headers)
    response = await client.post(
        f"/api/v1/leases/{lease['id']}/renew",
        json={"end_date": "2027-06-30", "rent_amount": 1650, "rent_frequency": "weekly"},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert float(body["rent_amount"]) == 1650.0
    assert body["rent_frequency"] == "weekly"


async def test_renewing_twice_is_rejected(client):
    headers = await landlord_headers(client)
    _, lease = await _make_lease(client, headers)
    first = await client.post(
        f"/api/v1/leases/{lease['id']}/renew",
        json={"end_date": "2027-12-31"},
        headers=headers,
    )
    assert first.status_code == 201
    second = await client.post(
        f"/api/v1/leases/{lease['id']}/renew",
        json={"end_date": "2028-12-31"},
        headers=headers,
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "Lease has already been renewed"


async def test_renew_rejects_overlapping_dates(client):
    headers = await landlord_headers(client)
    property_id, lease = await _make_lease(client, headers)
    # A second lease already occupies 2027, so the renewal cannot start in it.
    await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date="2027-01-01", end_date="2027-12-31"),
        headers=headers,
    )
    response = await client.post(
        f"/api/v1/leases/{lease['id']}/renew",
        json={"end_date": "2027-06-30"},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Lease dates overlap an existing lease"


async def test_renew_rejects_end_before_start(client):
    headers = await landlord_headers(client)
    _, lease = await _make_lease(client, headers)
    response = await client.post(
        f"/api/v1/leases/{lease['id']}/renew",
        json={"start_date": "2027-06-01", "end_date": "2027-01-01"},
        headers=headers,
    )
    assert response.status_code == 422


async def test_renew_other_org_lease_is_404(client):
    owner = await landlord_headers(client, "renew-owner@example.com")
    _, lease = await _make_lease(client, owner)
    stranger = await landlord_headers(client, "renew-stranger@example.com")
    response = await client.post(
        f"/api/v1/leases/{lease['id']}/renew",
        json={"end_date": "2027-12-31"},
        headers=stranger,
    )
    assert response.status_code == 404
    # Not just the status: a missing route also 404s, so this test would pass
    # against no isolation at all. The detail proves get_owned_lease refused it.
    assert response.json()["detail"] == "Lease not found"
