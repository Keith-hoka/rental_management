from sqlalchemy import select

from app.models import Invitation, LeaseTenant, User
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


async def invite_token(client, db_session, headers, lease_id, email) -> str:
    await client.post(f"/api/v1/leases/{lease_id}/invite", json={"email": email}, headers=headers)
    invite = (
        (await db_session.execute(select(Invitation).where(Invitation.email == email)))
        .scalars()
        .first()
    )
    return invite.token


async def accept(client, token, name="Tenant One", password="tenantpw1"):
    return await client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "name": name, "password": password},
    )


async def test_accept_tenant_creates_lease_tenant(client, db_session):
    headers = await landlord_headers(client, "acc-owner@example.com")
    lease_id = await make_lease(client, headers)
    token = await invite_token(client, db_session, headers, lease_id, "tina@example.com")

    response = await accept(client, token)
    assert response.status_code == 201
    tenant_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    me = await client.get("/api/v1/auth/me", headers=tenant_headers)
    assert me.json()["role"] == "tenant"

    links = (
        (await db_session.execute(select(LeaseTenant).where(LeaseTenant.lease_id == lease_id)))
        .scalars()
        .all()
    )
    assert len(links) == 1


async def test_two_co_tenants_join_one_lease(client, db_session):
    headers = await landlord_headers(client, "co-owner@example.com")
    lease_id = await make_lease(client, headers)
    t1 = await invite_token(client, db_session, headers, lease_id, "one@example.com")
    t2 = await invite_token(client, db_session, headers, lease_id, "two@example.com")
    assert (await accept(client, t1, name="One")).status_code == 201
    assert (await accept(client, t2, name="Two")).status_code == 201

    links = (
        (await db_session.execute(select(LeaseTenant).where(LeaseTenant.lease_id == lease_id)))
        .scalars()
        .all()
    )
    assert len(links) == 2


async def test_tenant_cannot_reach_management_endpoints(client, db_session):
    headers = await landlord_headers(client, "rbac-owner@example.com")
    lease_id = await make_lease(client, headers)
    token = await invite_token(client, db_session, headers, lease_id, "rbac-tenant@example.com")
    tenant_headers = {
        "Authorization": f"Bearer {(await accept(client, token)).json()['access_token']}"
    }

    assert (await client.get("/api/v1/properties", headers=tenant_headers)).status_code == 403
    assert (await client.get("/api/v1/leases", headers=tenant_headers)).status_code == 403
    invite_as_tenant = await client.post(
        f"/api/v1/leases/{lease_id}/invite",
        json={"email": "someone@example.com"},
        headers=tenant_headers,
    )
    assert invite_as_tenant.status_code == 403


async def test_list_lease_tenants_returns_joined(client, db_session):
    headers = await landlord_headers(client, "list-owner@example.com")
    lease_id = await make_lease(client, headers)
    token = await invite_token(client, db_session, headers, lease_id, "joined@example.com")
    await accept(client, token, name="Joined Tenant")

    response = await client.get(f"/api/v1/leases/{lease_id}/tenants", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert [t["email"] for t in body] == ["joined@example.com"]
    assert body[0]["name"] == "Joined Tenant"


async def test_list_lease_tenants_other_org_is_404(client):
    org_a = await landlord_headers(client, "lta@example.com")
    org_b = await landlord_headers(client, "ltb@example.com")
    lease_id = await make_lease(client, org_a)
    response = await client.get(f"/api/v1/leases/{lease_id}/tenants", headers=org_b)
    assert response.status_code == 404
