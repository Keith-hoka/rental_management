async def landlord_headers(client, email: str = "owner@example.com") -> dict:
    tokens = (
        await client.post(
            "/api/v1/auth/signup",
            json={
                "email": email,
                "password": "secret123",
                "name": "Owner",
                "organization_name": "Owner Org",
            },
        )
    ).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_create_invitation_returns_201(client):
    headers = await landlord_headers(client)
    response = await client.post(
        "/api/v1/invitations",
        json={"email": "pm@example.com", "role": "property_manager"},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "pm@example.com"
    assert body["role"] == "property_manager"
    assert body["status"] == "pending"


async def test_create_invitation_requires_auth(client):
    response = await client.post(
        "/api/v1/invitations", json={"email": "pm@example.com", "role": "property_manager"}
    )
    assert response.status_code == 401


async def test_create_invitation_rejects_tenant_role(client):
    headers = await landlord_headers(client)
    response = await client.post(
        "/api/v1/invitations",
        json={"email": "t@example.com", "role": "tenant"},
        headers=headers,
    )
    assert response.status_code == 422


async def test_list_invitations_is_org_scoped(client):
    org_a = await landlord_headers(client, "a@example.com")
    org_b = await landlord_headers(client, "b@example.com")
    await client.post(
        "/api/v1/invitations",
        json={"email": "pm@example.com", "role": "property_manager"},
        headers=org_a,
    )

    b_list = await client.get("/api/v1/invitations", headers=org_b)
    assert b_list.status_code == 200
    assert b_list.json() == []

    a_list = await client.get("/api/v1/invitations", headers=org_a)
    assert len(a_list.json()) == 1


async def test_revoke_invitation_removes_it_from_list(client):
    headers = await landlord_headers(client, "revoker@example.com")
    created = (
        await client.post(
            "/api/v1/invitations",
            json={"email": "pm@example.com", "role": "property_manager"},
            headers=headers,
        )
    ).json()

    revoked = await client.delete(f"/api/v1/invitations/{created['id']}", headers=headers)
    assert revoked.status_code == 204

    listed = await client.get("/api/v1/invitations", headers=headers)
    assert listed.json() == []


async def test_revoke_invitation_in_other_org_is_404(client):
    org_a = await landlord_headers(client, "a5@example.com")
    org_b = await landlord_headers(client, "b5@example.com")
    created = (
        await client.post(
            "/api/v1/invitations",
            json={"email": "pm@example.com", "role": "property_manager"},
            headers=org_a,
        )
    ).json()

    response = await client.delete(f"/api/v1/invitations/{created['id']}", headers=org_b)
    assert response.status_code == 404


async def test_duplicate_pending_invitation_is_rejected(client):
    headers = await landlord_headers(client, "dup@example.com")
    body = {"email": "pm@example.com", "role": "property_manager"}
    assert (await client.post("/api/v1/invitations", json=body, headers=headers)).status_code == 201

    second = await client.post("/api/v1/invitations", json=body, headers=headers)
    assert second.status_code == 409
    listed = (await client.get("/api/v1/invitations", headers=headers)).json()
    assert len(listed) == 1


async def test_invitation_can_be_reissued_after_revoke(client):
    headers = await landlord_headers(client, "reissue@example.com")
    body = {"email": "pm@example.com", "role": "property_manager"}
    first = (await client.post("/api/v1/invitations", json=body, headers=headers)).json()
    await client.delete(f"/api/v1/invitations/{first['id']}", headers=headers)

    again = await client.post("/api/v1/invitations", json=body, headers=headers)
    assert again.status_code == 201


async def test_same_email_can_be_invited_by_another_org(client):
    a = await landlord_headers(client, "org-a@example.com")
    b = await landlord_headers(client, "org-b@example.com")
    body = {"email": "pm@example.com", "role": "property_manager"}
    assert (await client.post("/api/v1/invitations", json=body, headers=a)).status_code == 201
    assert (await client.post("/api/v1/invitations", json=body, headers=b)).status_code == 201
