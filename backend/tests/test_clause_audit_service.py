import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.models import (
    Document,
    DocumentCategory,
    DocumentVersion,
    Lease,
    LeaseClauseAudit,
    LeaseFrequency,
    Membership,
    User,
)
from app.services import clause_audit
from tests.test_portal import make_lease
from tests.test_properties_crud import landlord_headers

FAKE_JOB = {
    "id": "11111111-1111-1111-1111-111111111111",
    "status": "pending",
    "jurisdiction": "NSW",
    "as_at": "2026-07-28",
    "engine_version": "1.1.1",
    "model": "claude-opus-4-8",
    "client_ref": None,
    "findings": [],
    "discrepancies": [],
    "error": None,
    "created_at": "2026-07-28T00:00:00Z",
    "completed_at": None,
}


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


def test_lease_fields_subset_and_none_omission():
    lease = Lease(
        rent_amount=Decimal(560),
        rent_frequency=LeaseFrequency.weekly,
        start_date=date(2026, 2, 1),
        end_date=date(2027, 1, 31),
        bond_amount=Decimal(2240),
    )
    fields = clause_audit.lease_fields(lease)
    assert fields["rent_amount"] == "560"
    assert fields["rent_frequency"] == "weekly"
    assert fields["start_date"] == "2026-02-01"
    assert fields["end_date"] == "2027-01-31"
    assert fields["bond_amount"] == "2240"
    assert "holding_deposit_amount" not in fields


async def test_submit_document_audit_posts_latest_version(
    client, db_session, tmp_path, monkeypatch
):
    email = "clausesubmit@example.com"
    headers = await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    lease_id = uuid.UUID(await make_lease(client, headers, "2 Submit St"))
    document = await _seed_document(db_session, org_id, lease_id, user_id)
    db_session.add(
        DocumentVersion(
            document_id=document.id,
            version_number=2,
            stored_name="v2.pdf",
            original_filename="lease-v2.pdf",
            content_type="application/pdf",
            size_bytes=20,
            uploaded_by=user_id,
        )
    )
    await db_session.commit()
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path))
    Path(tmp_path, "v2.pdf").write_bytes(b"%PDF-1.4 v2 bytes")

    captured = {}

    async def fake_create(filename, content, content_type, payload):
        captured.update(
            filename=filename, content=content, content_type=content_type, payload=payload
        )
        return FAKE_JOB

    monkeypatch.setattr("app.services.clause_audit.create_clause_audit", fake_create)
    lease = (await db_session.execute(select(Lease).where(Lease.id == lease_id))).scalar_one()

    row = await clause_audit.submit_document_audit(db_session, lease, document)
    await db_session.commit()

    assert captured["filename"] == "lease-v2.pdf"
    assert captured["content"] == b"%PDF-1.4 v2 bytes"
    assert captured["content_type"] == "application/pdf"
    assert captured["payload"]["jurisdiction"] == "NSW"
    assert captured["payload"]["client_ref"] == str(lease_id)
    assert captured["payload"]["lease"]["rent_amount"]
    assert row.job_id == FAKE_JOB["id"]
    assert row.status == "pending"
    assert row.model == "claude-opus-4-8" and row.engine_version == "1.1.1"
    version_2 = (
        await db_session.execute(
            select(DocumentVersion.id).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version_number == 2,
            )
        )
    ).scalar_one()
    assert row.document_version_id == version_2
