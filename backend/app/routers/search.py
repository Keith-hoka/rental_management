from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Document, Lease, MaintenanceRequest, Membership, Property
from app.routers.leases import manager
from app.schemas.search import SearchHit, SearchResults

router = APIRouter(prefix="/api/v1", tags=["search"])

LIMIT = 10


@router.get("/search", response_model=SearchResults)
async def search(
    q: str = "",
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> SearchResults:
    """Substring search across the org's properties, leases, maintenance and documents."""
    q = q.strip()
    if not q:
        return SearchResults(properties=[], leases=[], maintenance=[], documents=[])
    term = f"%{q}%"
    org = membership.organization_id

    properties = (
        (
            await session.execute(
                select(Property)
                .where(
                    Property.organization_id == org,
                    or_(Property.address.ilike(term), Property.description.ilike(term)),
                )
                .limit(LIMIT)
            )
        )
        .scalars()
        .all()
    )
    leases = (
        await session.execute(
            select(Lease, Property.address)
            .join(Property, Property.id == Lease.property_id)
            .where(
                Lease.organization_id == org,
                or_(Lease.tenant_name.ilike(term), Lease.tenant_email.ilike(term)),
            )
            .limit(LIMIT)
        )
    ).all()
    requests = (
        (
            await session.execute(
                select(MaintenanceRequest)
                .where(
                    MaintenanceRequest.organization_id == org,
                    or_(
                        MaintenanceRequest.title.ilike(term),
                        MaintenanceRequest.description.ilike(term),
                    ),
                )
                .limit(LIMIT)
            )
        )
        .scalars()
        .all()
    )
    documents = (
        (
            await session.execute(
                select(Document)
                .where(Document.organization_id == org, Document.title.ilike(term))
                .limit(LIMIT)
            )
        )
        .scalars()
        .all()
    )

    return SearchResults(
        properties=[
            SearchHit(title=p.address, subtitle=p.type.value, link=f"/app/properties/{p.id}")
            for p in properties
        ],
        leases=[
            SearchHit(title=lease.tenant_name, subtitle=address, link=f"/app/leases/{lease.id}")
            for lease, address in leases
        ],
        maintenance=[
            SearchHit(title=r.title, subtitle=r.status.value, link="/app/maintenance")
            for r in requests
        ],
        documents=[
            SearchHit(title=d.title, subtitle=d.category.value, link=f"/app/leases/{d.lease_id}")
            for d in documents
        ],
    )
