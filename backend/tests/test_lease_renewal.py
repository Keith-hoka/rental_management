import uuid

from sqlalchemy import select

from app.models import Lease
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def test_renewed_from_id_defaults_to_none(client, db_session):
    headers = await landlord_headers(client)
    property_id = await make_property(client, headers)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()
    lease = (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(created["id"])))
    ).scalar_one()
    assert lease.renewed_from_id is None
