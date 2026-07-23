import uuid

from sqlalchemy import select

from app.models import Document, DocumentCategory, DocumentVersion, Membership, User
from tests.test_portal import make_lease
from tests.test_properties_crud import landlord_headers


async def _org_and_user(db_session, email):
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    org_id = (
        await db_session.execute(
            select(Membership.organization_id).where(Membership.user_id == user.id)
        )
    ).scalar_one()
    return org_id, user.id


async def test_document_and_version_round_trip(client, db_session):
    email = "docmodel@example.com"
    headers = await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    lease_id = uuid.UUID(await make_lease(client, headers, "1 Doc St"))

    document = Document(
        organization_id=org_id,
        lease_id=lease_id,
        title="Signed Lease",
        category=DocumentCategory.lease,
        created_by=user_id,
    )
    db_session.add(document)
    await db_session.flush()
    db_session.add(
        DocumentVersion(
            document_id=document.id,
            version_number=1,
            stored_name="abc.pdf",
            original_filename="lease.pdf",
            content_type="application/pdf",
            size_bytes=1234,
            uploaded_by=user_id,
        )
    )
    await db_session.commit()

    stored = (
        await db_session.execute(select(Document).where(Document.id == document.id))
    ).scalar_one()
    assert stored.category == DocumentCategory.lease
    version = (
        await db_session.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        )
    ).scalar_one()
    assert version.version_number == 1
    assert version.original_filename == "lease.pdf"
