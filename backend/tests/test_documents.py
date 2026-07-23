import uuid

from sqlalchemy import select

from app.core.config import settings
from app.models import (
    Document,
    DocumentCategory,
    DocumentVersion,
    Membership,
    Notification,
    User,
)
from tests.test_portal import make_lease, onboard_tenant
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


PDF = b"%PDF-1.4 minimal"


async def _upload(client, headers, lease_id, tmp_path, monkeypatch, title="Signed Lease"):
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path))
    return await client.post(
        f"/api/v1/leases/{lease_id}/documents",
        data={"title": title, "category": "lease"},
        files={"file": ("lease.pdf", PDF, "application/pdf")},
        headers=headers,
    )


async def test_upload_creates_a_document_and_first_version(client, tmp_path, monkeypatch):
    headers = await landlord_headers(client, "docup@example.com")
    lease_id = await make_lease(client, headers, "1 Upload St")

    response = await _upload(client, headers, lease_id, tmp_path, monkeypatch)

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Signed Lease"
    assert body["category"] == "lease"
    assert body["version_count"] == 1
    assert body["current_version"]["version_number"] == 1
    assert list(tmp_path.iterdir())  # a file was written to the private dir


async def test_second_upload_is_version_two(client, tmp_path, monkeypatch):
    headers = await landlord_headers(client, "docv2@example.com")
    lease_id = await make_lease(client, headers, "2 Version Rd")
    doc_id = (await _upload(client, headers, lease_id, tmp_path, monkeypatch)).json()["id"]

    monkeypatch.setattr(settings, "documents_dir", str(tmp_path))
    response = await client.post(
        f"/api/v1/documents/{doc_id}/versions",
        files={"file": ("lease-v2.pdf", PDF, "application/pdf")},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["version_count"] == 2
    assert response.json()["current_version"]["version_number"] == 2


async def test_upload_rejects_unsupported_type(client, tmp_path, monkeypatch):
    headers = await landlord_headers(client, "docbad@example.com")
    lease_id = await make_lease(client, headers, "3 Bad St")
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path))

    response = await client.post(
        f"/api/v1/leases/{lease_id}/documents",
        data={"title": "Notes", "category": "other"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=headers,
    )

    assert response.status_code == 400


async def test_upload_notifies_the_tenant(client, db_session, tmp_path, monkeypatch):
    headers = await landlord_headers(client, "docnotify@example.com")
    lease_id = await make_lease(client, headers, "4 Notify St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "docnotify-t@example.com")

    await _upload(client, headers, lease_id, tmp_path, monkeypatch)

    rows = (
        (
            await db_session.execute(
                select(Notification).where(Notification.category == "document_uploaded")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    mine = (await client.get("/api/v1/me/notifications", headers=tenant)).json()
    assert any(n["category"] == "document_uploaded" for n in mine)
