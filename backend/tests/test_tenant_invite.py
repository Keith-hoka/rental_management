from app.models import LeaseTenant, User
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def make_lease(client, headers, property_address="1 Invite St") -> str:
    property_id = await make_property(client, headers, property_address)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()
    return created["id"]


async def test_invite_tenant_returns_201(client):
    headers = await landlord_headers(client, "inv-owner@example.com")
    lease_id = await make_lease(client, headers)
    response = await client.post(
        f"/api/v1/leases/{lease_id}/invite",
        json={"email": "tenant@example.com"},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "tenant@example.com"
    assert body["role"] == "tenant"


async def test_invite_tenant_requires_auth(client):
    headers = await landlord_headers(client, "inv-owner2@example.com")
    lease_id = await make_lease(client, headers)
    response = await client.post(
        f"/api/v1/leases/{lease_id}/invite", json={"email": "t@example.com"}
    )
    assert response.status_code == 401


async def test_invite_tenant_on_other_org_lease_is_404(client):
    org_a = await landlord_headers(client, "inva@example.com")
    org_b = await landlord_headers(client, "invb@example.com")
    lease_id = await make_lease(client, org_a)
    response = await client.post(
        f"/api/v1/leases/{lease_id}/invite", json={"email": "t@example.com"}, headers=org_b
    )
    assert response.status_code == 404


async def test_invite_tenant_already_a_tenant_is_409(client, db_session):
    headers = await landlord_headers(client, "dupe@example.com")
    lease_id = await make_lease(client, headers)
    user = User(email="already@example.com", hashed_password="x", name="Already")
    db_session.add(user)
    await db_session.flush()
    db_session.add(LeaseTenant(lease_id=lease_id, user_id=user.id))
    await db_session.commit()

    response = await client.post(
        f"/api/v1/leases/{lease_id}/invite",
        json={"email": "already@example.com"},
        headers=headers,
    )
    assert response.status_code == 409
