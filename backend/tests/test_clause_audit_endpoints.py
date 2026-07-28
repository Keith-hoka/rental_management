import uuid
from pathlib import Path

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.models import DocumentCategory, DocumentVersion, LeaseClauseAudit
from tests.test_clause_audit_service import FAKE_JOB, _org_and_user, _seed_document
from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers


async def _setup(client, db_session, email, address, tmp_path, monkeypatch):
    headers = await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    lease_id = uuid.UUID(await make_lease(client, headers, address))
    document = await _seed_document(db_session, org_id, lease_id, user_id)
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path))
    Path(tmp_path, "stored.pdf").write_bytes(b"%PDF-1.4 stored")
    return headers, lease_id, document


def _fake_create(monkeypatch):
    async def _fake(filename, content, content_type, payload):
        body = dict(FAKE_JOB)
        body["id"] = str(uuid.uuid4())
        return body

    monkeypatch.setattr("app.services.clause_audit.create_clause_audit", _fake)


async def test_post_disabled_is_503(client, db_session, tmp_path, monkeypatch):
    headers, lease_id, document = await _setup(
        client, db_session, "cl503@example.com", "10 Off St", tmp_path, monkeypatch
    )
    response = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    assert response.status_code == 503


async def test_post_creates_job_row(client, db_session, tmp_path, monkeypatch, compliance_on):
    headers, lease_id, document = await _setup(
        client, db_session, "cl202@example.com", "11 Run St", tmp_path, monkeypatch
    )
    _fake_create(monkeypatch)
    response = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["document_id"] == str(document.id)
    stored = (await db_session.execute(select(LeaseClauseAudit))).scalar_one()
    assert stored.job_id == body["job_id"]


async def test_post_foreign_document_is_404(
    client, db_session, tmp_path, monkeypatch, compliance_on
):
    headers, lease_id, _ = await _setup(
        client, db_session, "cl404@example.com", "12 Foreign St", tmp_path, monkeypatch
    )
    response = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{uuid.uuid4()}/clause-audit", headers=headers
    )
    assert response.status_code == 404


async def test_post_wrong_category_is_422(client, db_session, tmp_path, monkeypatch, compliance_on):
    headers, lease_id, document = await _setup(
        client, db_session, "cl422a@example.com", "13 Cat St", tmp_path, monkeypatch
    )
    document.category = DocumentCategory.report
    await db_session.commit()
    response = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    assert response.status_code == 422


async def test_post_non_pdf_is_422(client, db_session, tmp_path, monkeypatch, compliance_on):
    headers, lease_id, document = await _setup(
        client, db_session, "cl422b@example.com", "14 Png St", tmp_path, monkeypatch
    )
    version = (
        await db_session.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        )
    ).scalar_one()
    version.content_type = "image/png"
    await db_session.commit()
    response = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    assert response.status_code == 422


async def test_post_duplicate_in_flight_is_409(
    client, db_session, tmp_path, monkeypatch, compliance_on
):
    headers, lease_id, document = await _setup(
        client, db_session, "cl409@example.com", "15 Twice St", tmp_path, monkeypatch
    )
    _fake_create(monkeypatch)
    first = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    assert first.status_code == 202
    second = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    assert second.status_code == 409


async def test_post_service_429_passes_through(
    client, db_session, tmp_path, monkeypatch, compliance_on
):
    headers, lease_id, document = await _setup(
        client, db_session, "cl429@example.com", "16 Full St", tmp_path, monkeypatch
    )

    async def _full(filename, content, content_type, payload):
        request = httpx.Request("POST", "http://service/v1/clause-audits")
        response = httpx.Response(429, request=request)
        raise httpx.HTTPStatusError("too many", request=request, response=response)

    monkeypatch.setattr("app.services.clause_audit.create_clause_audit", _full)
    response = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    assert response.status_code == 429


async def test_tenant_role_is_403(client, db_session, tmp_path, monkeypatch, compliance_on):
    headers, lease_id, document = await _setup(
        client, db_session, "cl403@example.com", "18 Role St", tmp_path, monkeypatch
    )
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "cl403-t@example.com")
    posted = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=tenant
    )
    listed = await client.get(f"/api/v1/leases/{lease_id}/clause-audits", headers=tenant)
    assert posted.status_code == 403 and listed.status_code == 403


async def test_missing_file_on_disk_is_500(
    client, db_session, tmp_path, monkeypatch, compliance_on
):
    headers, lease_id, document = await _setup(
        client, db_session, "clnofile@example.com", "19 Gone St", tmp_path, monkeypatch
    )
    Path(tmp_path, "stored.pdf").unlink()
    response = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    assert response.status_code == 500
    assert "missing" in response.json()["detail"]


async def test_service_413_maps_to_413(client, db_session, tmp_path, monkeypatch, compliance_on):
    headers, lease_id, document = await _setup(
        client, db_session, "cl413@example.com", "20 Big St", tmp_path, monkeypatch
    )

    async def _too_big(filename, content, content_type, payload):
        request = httpx.Request("POST", "http://service/v1/clause-audits")
        response = httpx.Response(413, request=request)
        raise httpx.HTTPStatusError("too large", request=request, response=response)

    monkeypatch.setattr("app.services.clause_audit.create_clause_audit", _too_big)
    response = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    assert response.status_code == 413


async def test_list_shape_and_scoping(client, db_session, tmp_path, monkeypatch, compliance_on):
    headers, lease_id, document = await _setup(
        client, db_session, "cllist@example.com", "17 List St", tmp_path, monkeypatch
    )
    _fake_create(monkeypatch)
    await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    listed = await client.get(f"/api/v1/leases/{lease_id}/clause-audits", headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert body["enabled"] is True
    assert len(body["audits"]) == 1

    other_headers = await landlord_headers(client, "clother@example.com")
    foreign = await client.get(f"/api/v1/leases/{lease_id}/clause-audits", headers=other_headers)
    assert foreign.status_code == 404
