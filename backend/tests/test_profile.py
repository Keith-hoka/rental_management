from tests.test_properties_crud import landlord_headers


async def test_update_profile_sets_name_and_phone(client):
    headers = await landlord_headers(client, "profile@example.com")
    response = await client.patch(
        "/api/v1/auth/me", json={"name": "New Name", "phone": "555-9999"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"
    assert response.json()["phone"] == "555-9999"

    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["name"] == "New Name"
    assert me.json()["phone"] == "555-9999"


async def test_update_profile_requires_auth(client):
    response = await client.patch("/api/v1/auth/me", json={"phone": "1"})
    assert response.status_code == 401
