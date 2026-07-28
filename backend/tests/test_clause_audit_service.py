import uuid

from sqlalchemy import select

from app.models import (
    Document,
    DocumentCategory,
    DocumentVersion,
    LeaseClauseAudit,
    Membership,
    User,
)
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


async def _seed_document(db_session, org_id, lease_id, user_id, stored_name="stored.pdf"):
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
            stored_name=stored_name,
            original_filename="lease.pdf",
            content_type="application/pdf",
            size_bytes=16,
            uploaded_by=user_id,
        )
    )
    await db_session.commit()
    return document


async def test_lease_clause_audit_round_trip(client, db_session):
    email = "clausemodel@example.com"
    headers = await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    lease_id = uuid.UUID(await make_lease(client, headers, "1 Clause St"))
    document = await _seed_document(db_session, org_id, lease_id, user_id)
    version_id = (
        await db_session.execute(
            select(DocumentVersion.id).where(DocumentVersion.document_id == document.id)
        )
    ).scalar_one()

    row = LeaseClauseAudit(
        organization_id=org_id,
        lease_id=lease_id,
        document_id=document.id,
        document_version_id=version_id,
        job_id=str(uuid.uuid4()),
        status="pending",
        model="claude-opus-4-8",
        engine_version="1.1.1",
    )
    db_session.add(row)
    await db_session.commit()

    stored = (await db_session.execute(select(LeaseClauseAudit))).scalar_one()
    assert stored.status == "pending"
    assert stored.findings == [] and stored.discrepancies == []
    assert stored.completed_at is None
