from tests.test_properties_crud import NEW_PROPERTY, landlord_headers


async def test_list_only_returns_own_org(client):
    org_a = await landlord_headers(client, "a@example.com")
    org_b = await landlord_headers(client, "b@example.com")

    created = await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=org_a)
    assert created.status_code == 201

    b_list = await client.get("/api/v1/properties", headers=org_b)
    assert b_list.status_code == 200
    assert b_list.json() == []

    a_list = await client.get("/api/v1/properties", headers=org_a)
    assert a_list.status_code == 200
    assert len(a_list.json()) == 1


async def test_list_requires_auth(client):
    response = await client.get("/api/v1/properties")
    assert response.status_code == 401
