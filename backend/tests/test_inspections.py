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
from tests.test_leases import make_property
from tests.test_properties_crud import landlord_headers


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
