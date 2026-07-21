import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.models import Lease, LeaseFrequency, Organization, Property, PropertyType


async def test_create_lease(db_session):
    org = Organization(name="Keith Properties", currency="USD")
    db_session.add(org)
    await db_session.flush()

    prop = Property(organization_id=org.id, address="1 Main St", type=PropertyType.house)
    db_session.add(prop)
    await db_session.flush()

    lease = Lease(
        organization_id=org.id,
        property_id=prop.id,
        tenant_name="Tina Tenant",
        tenant_email="tina@example.com",
        rent_amount=Decimal("1500.00"),
        rent_frequency=LeaseFrequency.monthly,
        bond_amount=Decimal("3000.00"),
        notice_period_days=21,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    db_session.add(lease)
    await db_session.commit()

    found = (await db_session.execute(select(Lease).where(Lease.id == lease.id))).scalar_one()
    assert found.property_id == prop.id
    assert found.rent_frequency == LeaseFrequency.monthly
    assert found.rent_amount == Decimal("1500.00")
    assert found.start_date == date(2026, 1, 1)
    assert isinstance(found.id, uuid.UUID)


async def test_lease_roster_columns(db_session):
    org = Organization(name="Roster Org", currency="USD")
    db_session.add(org)
    await db_session.flush()
    prop = Property(organization_id=org.id, address="1 Roster St", type=PropertyType.house)
    db_session.add(prop)
    await db_session.flush()

    lease = Lease(
        organization_id=org.id,
        property_id=prop.id,
        tenant_name="Main Tenant",
        tenant_email="main@example.com",
        tenant_phone="555-1000",
        rent_amount=Decimal("1000.00"),
        rent_frequency=LeaseFrequency.monthly,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        co_tenants=[{"name": "Coco", "email": "coco@example.com", "phone": "555-2000"}],
    )
    db_session.add(lease)
    await db_session.commit()

    found = (await db_session.execute(select(Lease).where(Lease.id == lease.id))).scalar_one()
    assert found.tenant_phone == "555-1000"
    assert found.co_tenants == [{"name": "Coco", "email": "coco@example.com", "phone": "555-2000"}]
