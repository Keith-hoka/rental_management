from app.core.config import settings
from tests.test_properties_crud import NEW_PROPERTY, landlord_headers

PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00fake-png"


async def test_upload_image_appends_url(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    headers = await landlord_headers(client)
    created = (await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=headers)).json()

    response = await client.post(
        f"/api/v1/properties/{created['id']}/images",
        files={"file": ("photo.png", PNG_BYTES, "image/png")},
        headers=headers,
    )
    assert response.status_code == 200
    urls = response.json()["image_urls"]
    assert any(u.startswith("/uploads/") for u in urls)
    assert list(tmp_path.iterdir())  # a file was written


async def test_upload_rejects_non_image(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    headers = await landlord_headers(client)
    created = (await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=headers)).json()

    response = await client.post(
        f"/api/v1/properties/{created['id']}/images",
        files={"file": ("doc.txt", b"hello", "text/plain")},
        headers=headers,
    )
    assert response.status_code == 400


async def test_upload_image_in_other_org_is_404(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    org_a = await landlord_headers(client, "imga@example.com")
    org_b = await landlord_headers(client, "imgb@example.com")
    created = (await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=org_a)).json()

    response = await client.post(
        f"/api/v1/properties/{created['id']}/images",
        files={"file": ("photo.png", PNG_BYTES, "image/png")},
        headers=org_b,
    )
    assert response.status_code == 404
