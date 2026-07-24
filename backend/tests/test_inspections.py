import uuid
from datetime import date

from sqlalchemy import select

from app.models import (
    Inspection,
    InspectionCondition,
    InspectionItem,
    InspectionStatus,
    InspectionType,
)
from tests.test_calendar import _org_and_user
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


def _body(property_id, **kw) -> dict:
    body = {
        "property_id": property_id,
        "type": "move_in",
        "scheduled_for": "2026-08-01",
        "items": [{"area": "Kitchen", "condition": "good"}],
    }
    body.update(kw)
    return body


async def make_lease(client, headers, property_id) -> str:
    """Create a lease via the API and return its id."""
    response = await client.post(
        f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
    )
    return response.json()["id"]


async def test_inspection_round_trip(client, db_session):
    email = "inspmodel@example.com"
    headers = await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    property_id = await make_property(client, headers, "1 Inspect St")
    inspection = Inspection(
        organization_id=org_id,
        property_id=uuid.UUID(property_id),
        type=InspectionType.move_in,
        status=InspectionStatus.scheduled,
        scheduled_for=date(2026, 8, 1),
        created_by=user_id,
    )
    db_session.add(inspection)
    await db_session.flush()
    db_session.add(
        InspectionItem(
            inspection_id=inspection.id,
            position=0,
            area="Kitchen",
            condition=InspectionCondition.good,
        )
    )
    await db_session.commit()

    stored = (
        await db_session.execute(select(Inspection).where(Inspection.id == inspection.id))
    ).scalar_one()
    assert stored.status == InspectionStatus.scheduled
    assert stored.image_urls == []
    item = (
        await db_session.execute(
            select(InspectionItem).where(InspectionItem.inspection_id == inspection.id)
        )
    ).scalar_one()
    assert item.area == "Kitchen"
    assert item.condition == InspectionCondition.good


async def test_create_inspection_with_items(client):
    headers = await landlord_headers(client, "insp1@example.com")
    property_id = await make_property(client, headers, "2 Inspect St")
    resp = await client.post(
        "/api/v1/inspections",
        json=_body(
            property_id,
            items=[
                {"area": "Kitchen", "condition": "good"},
                {"area": "Bathroom", "condition": "fair", "note": "cracked tile"},
            ],
        ),
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "scheduled"
    assert body["type"] == "move_in"
    assert [i["area"] for i in body["items"]] == ["Kitchen", "Bathroom"]
    assert body["items"][1]["condition"] == "fair"
    assert body["items"][1]["note"] == "cracked tile"
    assert body["image_urls"] == []


async def test_create_inspection_foreign_property_400(client):
    org_a = await landlord_headers(client, "inspa@example.com")
    org_b = await landlord_headers(client, "inspb@example.com")
    property_id = await make_property(client, org_a, "3 Inspect St")
    resp = await client.post("/api/v1/inspections", json=_body(property_id), headers=org_b)
    assert resp.status_code == 400


async def test_create_inspection_foreign_lease_400(client):
    org_a = await landlord_headers(client, "inspla@example.com")
    org_b = await landlord_headers(client, "insplb@example.com")
    prop_a = await make_property(client, org_a, "4 Inspect St")
    lease_id = await make_lease(client, org_a, prop_a)
    prop_b = await make_property(client, org_b, "5 Inspect St")
    resp = await client.post(
        "/api/v1/inspections", json=_body(prop_b, lease_id=lease_id), headers=org_b
    )
    assert resp.status_code == 400


async def test_list_inspections_filtered_by_property(client):
    headers = await landlord_headers(client, "insplist@example.com")
    prop1 = await make_property(client, headers, "6 Inspect St")
    prop2 = await make_property(client, headers, "7 Inspect St")
    await client.post("/api/v1/inspections", json=_body(prop1), headers=headers)
    await client.post("/api/v1/inspections", json=_body(prop2), headers=headers)
    all_resp = await client.get("/api/v1/inspections", headers=headers)
    assert len(all_resp.json()) == 2
    filtered = await client.get(f"/api/v1/inspections?property_id={prop1}", headers=headers)
    body = filtered.json()
    assert len(body) == 1
    assert body[0]["property_id"] == prop1


async def test_patch_inspection_status(client):
    headers = await landlord_headers(client, "insppatch@example.com")
    property_id = await make_property(client, headers, "8 Inspect St")
    created = (
        await client.post("/api/v1/inspections", json=_body(property_id), headers=headers)
    ).json()
    resp = await client.patch(
        f"/api/v1/inspections/{created['id']}",
        json={"status": "completed"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


async def test_patch_inspection_items_replaces(client):
    headers = await landlord_headers(client, "inspreplace@example.com")
    property_id = await make_property(client, headers, "9 Inspect St")
    created = (
        await client.post("/api/v1/inspections", json=_body(property_id), headers=headers)
    ).json()
    resp = await client.patch(
        f"/api/v1/inspections/{created['id']}",
        json={"items": [{"area": "Garage", "condition": "poor"}]},
        headers=headers,
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["area"] == "Garage"
    assert items[0]["condition"] == "poor"


async def test_patch_inspection_without_items_keeps_them(client):
    headers = await landlord_headers(client, "inspkeep@example.com")
    property_id = await make_property(client, headers, "10 Inspect St")
    created = (
        await client.post("/api/v1/inspections", json=_body(property_id), headers=headers)
    ).json()
    resp = await client.patch(
        f"/api/v1/inspections/{created['id']}",
        json={"note": "done"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["note"] == "done"
    assert [i["area"] for i in body["items"]] == ["Kitchen"]


async def test_delete_inspection(client):
    headers = await landlord_headers(client, "inspdel@example.com")
    property_id = await make_property(client, headers, "11 Inspect St")
    created = (
        await client.post("/api/v1/inspections", json=_body(property_id), headers=headers)
    ).json()
    resp = await client.delete(f"/api/v1/inspections/{created['id']}", headers=headers)
    assert resp.status_code == 204
    listed = await client.get("/api/v1/inspections", headers=headers)
    assert listed.json() == []


async def test_cross_org_patch_and_delete_404(client):
    org_a = await landlord_headers(client, "inspxa@example.com")
    org_b = await landlord_headers(client, "inspxb@example.com")
    property_id = await make_property(client, org_a, "12 Inspect St")
    created = (
        await client.post("/api/v1/inspections", json=_body(property_id), headers=org_a)
    ).json()
    patch = await client.patch(
        f"/api/v1/inspections/{created['id']}",
        json={"status": "completed"},
        headers=org_b,
    )
    assert patch.status_code == 404
    delete = await client.delete(f"/api/v1/inspections/{created['id']}", headers=org_b)
    assert delete.status_code == 404
