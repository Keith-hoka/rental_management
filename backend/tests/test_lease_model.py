import uuid
from datetime import UTC, date, datetime, timedelta
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


async def test_lease_tenant_link_and_cascade(db_session):
    from app.models import Invitation, InvitationStatus, LeaseTenant, Role, User

    org = Organization(name="Cascade Org", currency="USD")
    db_session.add(org)
    await db_session.flush()
    prop = Property(organization_id=org.id, address="1 Cascade St", type=PropertyType.house)
    db_session.add(prop)
    await db_session.flush()
    lease = Lease(
        organization_id=org.id,
        property_id=prop.id,
        tenant_name="T",
        tenant_email="t@example.com",
        rent_amount=Decimal("1000.00"),
        rent_frequency=LeaseFrequency.monthly,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    user = User(email="tenant@example.com", hashed_password="x", name="Tenant")
    db_session.add_all([lease, user])
    await db_session.flush()

    db_session.add(LeaseTenant(lease_id=lease.id, user_id=user.id))
    db_session.add(
        Invitation(
            organization_id=org.id,
            email="tenant@example.com",
            role=Role.tenant,
            lease_id=lease.id,
            token="cascade-tok",
            status=InvitationStatus.pending,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
    )
    await db_session.commit()

    await db_session.delete(lease)
    await db_session.commit()
    assert (
        await db_session.execute(select(LeaseTenant).where(LeaseTenant.lease_id == lease.id))
    ).first() is None
    assert (
        await db_session.execute(select(Invitation).where(Invitation.lease_id == lease.id))
    ).first() is None
