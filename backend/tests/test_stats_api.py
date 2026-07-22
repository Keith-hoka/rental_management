from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers


async def test_stats_endpoint(client):
    headers = await landlord_headers(client, "statsapi@example.com")
    response = await client.get("/api/v1/stats", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["properties_total"] == 0
    assert len(body["monthly_income"]) == 6


async def test_monthly_income_amount_is_a_json_number(client):
    """Recharts cannot plot strings, so the chart series must not be Decimal-as-string."""
    headers = await landlord_headers(client, "statsnum@example.com")
    body = (await client.get("/api/v1/stats", headers=headers)).json()
    assert isinstance(body["monthly_income"][0]["amount"], (int, float))


async def test_stats_requires_auth(client):
    response = await client.get("/api/v1/stats")
    assert response.status_code == 401


async def test_stats_forbidden_for_tenant(client, db_session):
    headers = await landlord_headers(client, "statsttl@example.com")
    lease_id = await make_lease(client, headers, "Stats St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "statst@example.com")
    response = await client.get("/api/v1/stats", headers=tenant)
    assert response.status_code == 403
