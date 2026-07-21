import uuid
from datetime import datetime

from app.models import LeaseReminder
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _make_lease_id(client, headers, property_id) -> str:
    return (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()["id"]


async def test_reminder_history_newest_first(client, db_session):
    headers = await landlord_headers(client, "rh@example.com")
    property_id = await make_property(client, headers)
    lease_id = await _make_lease_id(client, headers, property_id)

    older = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    newer = datetime.fromisoformat("2026-02-01T00:00:00+00:00")
    db_session.add(LeaseReminder(lease_id=uuid.UUID(lease_id), threshold_days=60, sent_at=older))
    db_session.add(LeaseReminder(lease_id=uuid.UUID(lease_id), threshold_days=30, sent_at=newer))
    await db_session.commit()

    response = await client.get(f"/api/v1/leases/{lease_id}/reminders", headers=headers)
    assert response.status_code == 200
    assert [r["threshold_days"] for r in response.json()] == [30, 60]


async def test_reminder_history_cross_org_is_404(client):
    org_a = await landlord_headers(client, "rha@example.com")
    org_b = await landlord_headers(client, "rhb@example.com")
    property_id = await make_property(client, org_a)
    lease_id = await _make_lease_id(client, org_a, property_id)
    response = await client.get(f"/api/v1/leases/{lease_id}/reminders", headers=org_b)
    assert response.status_code == 404


async def test_reminder_history_requires_auth(client):
    headers = await landlord_headers(client, "rhauth@example.com")
    property_id = await make_property(client, headers)
    lease_id = await _make_lease_id(client, headers, property_id)
    response = await client.get(f"/api/v1/leases/{lease_id}/reminders")
    assert response.status_code == 401
