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
    # The whole history is returned, newest first, so old versions stay reachable.
    assert [v["version_number"] for v in response.json()["versions"]] == [2, 1]


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


async def test_list_documents_for_a_lease(client, tmp_path, monkeypatch):
    headers = await landlord_headers(client, "doclist@example.com")
    lease_id = await make_lease(client, headers, "5 List St")
    await _upload(client, headers, lease_id, tmp_path, monkeypatch, title="Report")

    body = (await client.get(f"/api/v1/leases/{lease_id}/documents", headers=headers)).json()

    assert [d["title"] for d in body] == ["Report"]
    assert body[0]["version_count"] == 1


async def test_other_orgs_document_is_404(client, tmp_path, monkeypatch):
    owner = await landlord_headers(client, "docowner@example.com")
    lease_id = await make_lease(client, owner, "6 Mine St")
    doc_id = (await _upload(client, owner, lease_id, tmp_path, monkeypatch)).json()["id"]

    stranger = await landlord_headers(client, "docthief@example.com")
    assert (
        await client.get(f"/api/v1/documents/{doc_id}/versions", headers=stranger)
    ).status_code == 404
    assert (await client.delete(f"/api/v1/documents/{doc_id}", headers=stranger)).status_code == 404


async def test_delete_removes_document_versions_and_files(
    client, db_session, tmp_path, monkeypatch
):
    headers = await landlord_headers(client, "docdel@example.com")
    lease_id = await make_lease(client, headers, "7 Del St")
    doc_id = (await _upload(client, headers, lease_id, tmp_path, monkeypatch)).json()["id"]
    assert list(tmp_path.iterdir())  # the file exists before delete

    assert (await client.delete(f"/api/v1/documents/{doc_id}", headers=headers)).status_code == 204

    gone = (
        await db_session.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
    ).scalar_one_or_none()
    assert gone is None
    versions = (
        (
            await db_session.execute(
                select(DocumentVersion).where(DocumentVersion.document_id == uuid.UUID(doc_id))
            )
        )
        .scalars()
        .all()
    )
    assert versions == []
    assert list(tmp_path.iterdir()) == []  # the file was unlinked


async def test_tenant_lists_own_lease_documents(client, db_session, tmp_path, monkeypatch):
    headers = await landlord_headers(client, "doctenant@example.com")
    lease_id = await make_lease(client, headers, "8 Tenant St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "doctenant-t@example.com")
    await _upload(client, headers, lease_id, tmp_path, monkeypatch, title="Your Lease")

    body = (await client.get(f"/api/v1/me/leases/{lease_id}/documents", headers=tenant)).json()

    assert [d["title"] for d in body] == ["Your Lease"]


async def test_manager_downloads_the_file(client, tmp_path, monkeypatch):
    headers = await landlord_headers(client, "docdl@example.com")
    lease_id = await make_lease(client, headers, "9 Download St")
    version_id = (await _upload(client, headers, lease_id, tmp_path, monkeypatch)).json()[
        "current_version"
    ]["id"]

    response = await client.get(
        f"/api/v1/documents/versions/{version_id}/download", headers=headers
    )

    assert response.status_code == 200
    assert response.content == PDF
    assert response.headers["content-type"].startswith("application/pdf")


async def test_tenant_of_another_lease_cannot_download(client, db_session, tmp_path, monkeypatch):
    owner = await landlord_headers(client, "dlowner@example.com")
    lease_id = await make_lease(client, owner, "10 Private St")
    version_id = (await _upload(client, owner, lease_id, tmp_path, monkeypatch)).json()[
        "current_version"
    ]["id"]

    other_mgr = await landlord_headers(client, "dlother@example.com")
    other_lease = await make_lease(client, other_mgr, "11 Other St")
    stranger = await onboard_tenant(
        client, db_session, other_mgr, other_lease, "dlstranger@example.com"
    )

    response = await client.get(
        f"/api/v1/documents/versions/{version_id}/download", headers=stranger
    )
    assert response.status_code == 404


async def test_unauthenticated_download_is_rejected(client, tmp_path, monkeypatch):
    headers = await landlord_headers(client, "dlnoauth@example.com")
    lease_id = await make_lease(client, headers, "12 NoAuth St")
    version_id = (await _upload(client, headers, lease_id, tmp_path, monkeypatch)).json()[
        "current_version"
    ]["id"]

    response = await client.get(f"/api/v1/documents/versions/{version_id}/download")
    assert response.status_code == 401
