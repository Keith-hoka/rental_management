import uuid

from sqlalchemy import select

from app.models import Organization, Property, PropertyStatus, PropertyType


async def test_create_property(db_session):
    org = Organization(name="Keith Properties", currency="USD")
    db_session.add(org)
    await db_session.flush()

    prop = Property(
        organization_id=org.id,
        address="1 Main St",
        type=PropertyType.house,
        bedrooms=3,
        bathrooms=2,
        parking=1,
        description="Nice",
        status=PropertyStatus.vacant,
        image_urls=["http://img/1.jpg"],
    )
    db_session.add(prop)
    await db_session.commit()

    found = (await db_session.execute(select(Property).where(Property.id == prop.id))).scalar_one()
    assert found.organization_id == org.id
    assert found.type == PropertyType.house
    assert found.status == PropertyStatus.vacant
    assert found.image_urls == ["http://img/1.jpg"]
    assert isinstance(found.id, uuid.UUID)
