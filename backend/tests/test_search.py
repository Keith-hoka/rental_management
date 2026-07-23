import uuid
from datetime import date, timedelta

from app.core.config import settings
from app.models import MaintenanceRequest
from tests.test_calendar import _org_and_user
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _seed(client, db_session, email, marker):
    """A property, lease and maintenance request all containing marker."""
    headers = await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    property_id = await make_property(client, headers, f"1 {marker} St")
    today = date.today()
    lease_id = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(
                tenant_name=f"Tina {marker}",
                tenant_email=f"tina-{marker.lower()}@example.com",
                start_date=str(today - timedelta(days=1)),
                end_date=str(today + timedelta(days=30)),
            ),
            headers=headers,
        )
    ).json()["id"]
    db_session.add(
        MaintenanceRequest(
            organization_id=org_id,
            property_id=uuid.UUID(property_id),
            lease_id=uuid.UUID(lease_id),
            created_by=user_id,
            title=f"Fix {marker} tap",
            description="Kitchen",
        )
    )
    await db_session.commit()
    return headers, property_id, lease_id


async def test_search_finds_all_groups(client, db_session, tmp_path, monkeypatch):
    headers, property_id, lease_id = await _seed(client, db_session, "srchall@example.com", "Zebra")
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path))
    await client.post(
        f"/api/v1/leases/{lease_id}/documents",
        data={"title": "Zebra lease scan", "category": "lease"},
        files={"file": ("z.pdf", b"%PDF-1.4 z", "application/pdf")},
        headers=headers,
    )

    body = (await client.get("/api/v1/search?q=zebra", headers=headers)).json()

    assert [h["link"] for h in body["properties"]] == [f"/app/properties/{property_id}"]
    assert [h["link"] for h in body["leases"]] == [f"/app/leases/{lease_id}"]
    assert body["maintenance"][0]["title"] == "Fix Zebra tap"
    assert body["documents"][0]["link"] == f"/app/leases/{lease_id}"


async def test_search_is_org_scoped(client, db_session):
    await _seed(client, db_session, "srchowner@example.com", "Quokka")
    stranger = await landlord_headers(client, "srchthief@example.com")
    body = (await client.get("/api/v1/search?q=quokka", headers=stranger)).json()
    assert body == {"properties": [], "leases": [], "maintenance": [], "documents": []}


async def test_search_empty_query_returns_nothing(client):
    headers = await landlord_headers(client, "srchempty@example.com")
    body = (await client.get("/api/v1/search?q=", headers=headers)).json()
    assert body == {"properties": [], "leases": [], "maintenance": [], "documents": []}


async def test_search_no_match(client, db_session):
    headers, _, _ = await _seed(client, db_session, "srchnone@example.com", "Walrus")
    body = (await client.get("/api/v1/search?q=xyzzy", headers=headers)).json()
    assert body == {"properties": [], "leases": [], "maintenance": [], "documents": []}
