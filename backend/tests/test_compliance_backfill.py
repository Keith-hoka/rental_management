"""Tests for the never-audited backfill and --fix-jurisdictions."""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.compliance_backfill import _print_report, backfill, fix_jurisdictions, main
from app.models import (
    Document,
    DocumentCategory,
    DocumentVersion,
    LeaseAudit,
    LeaseClauseAudit,
    Property,
    User,
)
from app.services import clause_audit
from tests.test_lease_model import make_lease_row


async def _set_state(db_session, lease, state):
    """Set the state on the lease's property and flush."""
    prop = (
        await db_session.execute(select(Property).where(Property.id == lease.property_id))
    ).scalar_one()
    prop.state = state
    await db_session.flush()


def _audit(lease, jurisdiction):
    return LeaseAudit(
        lease_id=lease.id,
        organization_id=lease.organization_id,
        audit_id=uuid.uuid4(),
        as_at=date(2026, 7, 27),
        findings=[],
        jurisdiction=jurisdiction,
    )


async def _seed_document(db_session, lease, user):
    document = Document(
        organization_id=lease.organization_id,
        lease_id=lease.id,
        title="Signed Lease",
        category=DocumentCategory.lease,
        created_by=user.id,
    )
    db_session.add(document)
    await db_session.flush()
    version = DocumentVersion(
        document_id=document.id,
        version_number=1,
        stored_name="stored.pdf",
        original_filename="lease.pdf",
        content_type="application/pdf",
        size_bytes=16,
        uploaded_by=user.id,
    )
    db_session.add(version)
    await db_session.flush()
    return document, version


def _clause_audit(lease, document, version, jurisdiction, status="succeeded", created_at=None):
    audit = LeaseClauseAudit(
        organization_id=lease.organization_id,
        lease_id=lease.id,
        document_id=document.id,
        document_version_id=version.id,
        job_id=str(uuid.uuid4()),
        status=status,
        model="claude-opus-4-8",
        engine_version="1.1.1",
        jurisdiction=jurisdiction,
    )
    if created_at is not None:
        audit.created_at = created_at
    return audit


async def test_fix_jurisdictions_selects_mismatched_leases(db_session, monkeypatch):
    mismatched_lease = await make_lease_row(db_session)
    await _set_state(db_session, mismatched_lease, "Victoria")
    db_session.add(_audit(mismatched_lease, "NSW"))

    matching_lease = await make_lease_row(db_session)
    await _set_state(db_session, matching_lease, "VIC")
    db_session.add(_audit(matching_lease, "VIC"))

    missing_lease = await make_lease_row(db_session)

    qld_lease = await make_lease_row(db_session)
    await _set_state(db_session, qld_lease, "QLD")

    await db_session.commit()

    enqueued = []

    async def fake_enqueue(session, lease_id):
        enqueued.append(lease_id)

    monkeypatch.setattr("app.compliance_backfill.enqueue_audit", fake_enqueue)
    report = await fix_jurisdictions(db_session, execute=True)
    assert enqueued == [mismatched_lease.id]
    assert report["deterministic_enqueued"] == 1
    assert report["skipped_matching_audits"] == 1
    assert report["missing"] == [missing_lease.id]
    assert report["unsupported"] == [qld_lease.id]


async def test_fix_jurisdictions_resubmits_mismatched_clause_audit(db_session, monkeypatch):
    user = User(email="fixjuris-clause@example.com", hashed_password="x", name="Fixer")
    db_session.add(user)
    await db_session.flush()

    mismatched_lease = await make_lease_row(db_session)
    await _set_state(db_session, mismatched_lease, "Victoria")
    document, version = await _seed_document(db_session, mismatched_lease, user)
    db_session.add(_clause_audit(mismatched_lease, document, version, "NSW"))

    matching_lease = await make_lease_row(db_session)
    await _set_state(db_session, matching_lease, "Victoria")
    matching_document, matching_version = await _seed_document(db_session, matching_lease, user)
    db_session.add(_clause_audit(matching_lease, matching_document, matching_version, "VIC"))

    await db_session.commit()

    calls = []

    async def fake_submit(session, lease_arg, document_arg, version_arg):
        calls.append((lease_arg.id, document_arg.id, version_arg.id))

    monkeypatch.setattr("app.services.clause_audit.submit_document_audit", fake_submit)

    report = await fix_jurisdictions(db_session, execute=True)

    assert calls == [(mismatched_lease.id, document.id, version.id)]
    assert report["clause_resubmitted"] == 1
    assert report["skipped_matching_clause"] == 1
    assert report["skipped_matching_audits"] == 0


async def test_fix_jurisdictions_skips_resubmit_when_latest_clause_audit_already_matches(
    db_session, monkeypatch
):
    """Latest-per-document dedup must key off created_at, not row order.

    This is the exact shape a completed --fix-jurisdictions run leaves behind:
    one document with two clause audits, the newer one already corrected to
    VIC and an older stale NSW row still sitting underneath it. A repeat run
    must recognise the document as already fixed via the newest row, or every
    previously-fixed document gets resubmitted and burns LLM quota.
    """
    user = User(email="fixjuris-dedup@example.com", hashed_password="x", name="Dedup")
    db_session.add(user)
    await db_session.flush()

    lease = await make_lease_row(db_session)
    await _set_state(db_session, lease, "Victoria")
    document, version = await _seed_document(db_session, lease, user)

    older_at = datetime(2026, 7, 20, 9, 0, tzinfo=UTC)
    newer_at = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)
    db_session.add(_clause_audit(lease, document, version, "NSW", created_at=older_at))
    db_session.add(_clause_audit(lease, document, version, "VIC", created_at=newer_at))

    await db_session.commit()

    calls = []

    async def fake_submit(session, lease_arg, document_arg, version_arg):
        calls.append((lease_arg.id, document_arg.id, version_arg.id))

    monkeypatch.setattr("app.services.clause_audit.submit_document_audit", fake_submit)

    report = await fix_jurisdictions(db_session, execute=True)

    assert calls == []
    assert report["clause_resubmitted"] == 0
    assert report["skipped_matching_clause"] == 1


async def test_fix_jurisdictions_dry_run_reports_without_side_effects(db_session, monkeypatch):
    user = User(email="fixjuris-dryrun@example.com", hashed_password="x", name="Dry Run")
    db_session.add(user)
    await db_session.flush()

    lease = await make_lease_row(db_session)
    await _set_state(db_session, lease, "Victoria")
    db_session.add(_audit(lease, "NSW"))
    document, version = await _seed_document(db_session, lease, user)
    db_session.add(_clause_audit(lease, document, version, "NSW"))
    await db_session.commit()

    enqueued = []
    submitted = []

    async def fake_enqueue(session, lease_id):
        enqueued.append(lease_id)

    async def fake_submit(session, lease_arg, document_arg, version_arg):
        submitted.append(lease_arg.id)

    monkeypatch.setattr("app.compliance_backfill.enqueue_audit", fake_enqueue)
    monkeypatch.setattr("app.services.clause_audit.submit_document_audit", fake_submit)

    report = await fix_jurisdictions(db_session)

    assert enqueued == []
    assert submitted == []
    assert report["deterministic_enqueued"] == 1
    assert report["clause_resubmitted"] == 1


@pytest.mark.parametrize("execute", [False, True])
async def test_fix_jurisdictions_counts_documents_without_versions(
    db_session, monkeypatch, execute
):
    """A document with no stored version is never a resubmit, in either mode."""
    user = User(email=f"fixjuris-noversion-{execute}@example.com", hashed_password="x", name="NV")
    db_session.add(user)
    await db_session.flush()

    lease = await make_lease_row(db_session)
    await _set_state(db_session, lease, "Victoria")
    document, version = await _seed_document(db_session, lease, user)
    db_session.add(_clause_audit(lease, document, version, "NSW"))
    await db_session.commit()

    async def fake_latest_version(session, document_id):
        return None

    submitted = []

    async def fake_submit(session, lease_arg, document_arg, version_arg):
        submitted.append(lease_arg.id)

    monkeypatch.setattr("app.services.clause_audit.latest_version", fake_latest_version)
    monkeypatch.setattr("app.services.clause_audit.submit_document_audit", fake_submit)

    report = await fix_jurisdictions(db_session, execute=execute)

    assert submitted == []
    assert report["clause_resubmitted"] == 0
    assert report["skipped_no_version"] == 1


@pytest.mark.parametrize("execute", [False, True])
async def test_fix_jurisdictions_skips_documents_with_in_flight_audits(
    db_session, monkeypatch, execute
):
    """Mirror the router's IN_FLIGHT guard: never double-submit a running document."""
    user = User(email=f"fixjuris-inflight-{execute}@example.com", hashed_password="x", name="IF")
    db_session.add(user)
    await db_session.flush()

    lease = await make_lease_row(db_session)
    await _set_state(db_session, lease, "Victoria")
    document, version = await _seed_document(db_session, lease, user)
    db_session.add(_clause_audit(lease, document, version, "NSW", status="pending"))
    await db_session.commit()

    submitted = []

    async def fake_submit(session, lease_arg, document_arg, version_arg):
        submitted.append(lease_arg.id)

    monkeypatch.setattr("app.services.clause_audit.submit_document_audit", fake_submit)

    report = await fix_jurisdictions(db_session, execute=execute)

    assert submitted == []
    assert report["clause_resubmitted"] == 0
    assert report["skipped_in_flight"] == 1


async def test_fix_jurisdictions_isolates_clause_read_errors(db_session, monkeypatch):
    """A transient read failure in the clause branch lands in errors, not a crash."""
    user = User(email="fixjuris-readerr@example.com", hashed_password="x", name="Read Err")
    db_session.add(user)
    await db_session.flush()

    failing_lease = await make_lease_row(db_session)
    await _set_state(db_session, failing_lease, "Victoria")
    failing_document, failing_version = await _seed_document(db_session, failing_lease, user)
    db_session.add(_clause_audit(failing_lease, failing_document, failing_version, "NSW"))

    ok_lease = await make_lease_row(db_session)
    await _set_state(db_session, ok_lease, "Victoria")
    ok_document, ok_version = await _seed_document(db_session, ok_lease, user)
    db_session.add(_clause_audit(ok_lease, ok_document, ok_version, "NSW"))

    await db_session.commit()
    failing_document_id = failing_document.id
    failing_lease_id = failing_lease.id
    ok_lease_id = ok_lease.id

    real_latest_version = clause_audit.latest_version

    async def flaky_latest_version(session, document_id):
        if document_id == failing_document_id:
            raise RuntimeError("read boom")
        return await real_latest_version(session, document_id)

    submitted = []

    async def fake_submit(session, lease_arg, document_arg, version_arg):
        submitted.append(lease_arg.id)

    monkeypatch.setattr("app.services.clause_audit.latest_version", flaky_latest_version)
    monkeypatch.setattr("app.services.clause_audit.submit_document_audit", fake_submit)

    report = await fix_jurisdictions(db_session, execute=True)

    assert report["errors"] == [failing_lease_id]
    assert submitted == [ok_lease_id]
    assert report["clause_resubmitted"] == 1


async def test_fix_jurisdictions_execute_isolates_clause_errors(db_session, monkeypatch):
    """One resubmit failing must not roll back an earlier resubmit's commit."""
    user = User(email="fixjuris-errors@example.com", hashed_password="x", name="Errors")
    db_session.add(user)
    await db_session.flush()

    ok_lease = await make_lease_row(db_session)
    await _set_state(db_session, ok_lease, "Victoria")
    ok_document, ok_version = await _seed_document(db_session, ok_lease, user)
    db_session.add(_clause_audit(ok_lease, ok_document, ok_version, "NSW"))

    failing_lease = await make_lease_row(db_session)
    await _set_state(db_session, failing_lease, "Victoria")
    failing_document, failing_version = await _seed_document(db_session, failing_lease, user)
    db_session.add(_clause_audit(failing_lease, failing_document, failing_version, "NSW"))

    await db_session.commit()

    ok_lease_id = ok_lease.id
    failing_lease_id = failing_lease.id

    calls = []

    async def fake_submit(session, lease_arg, document_arg, version_arg):
        calls.append(lease_arg.id)
        if lease_arg.id == failing_lease_id:
            raise RuntimeError("submit boom")
        session.add(_clause_audit(lease_arg, document_arg, version_arg, "VIC"))

    monkeypatch.setattr("app.services.clause_audit.submit_document_audit", fake_submit)

    report = await fix_jurisdictions(db_session, execute=True)

    assert set(calls) == {ok_lease_id, failing_lease_id}
    assert report["errors"] == [failing_lease_id]
    assert report["clause_resubmitted"] == 1
    assert report["skipped_matching_audits"] == 0
    assert report["skipped_matching_clause"] == 0
    assert report["deterministic_enqueued"] == 0

    # Prove the successful resubmit is durably committed, not merely pending
    # in-session: roll back this session's own (now-empty) transaction and
    # re-query. A row that survives an unrelated rollback was truly committed.
    await db_session.rollback()
    persisted = (
        await db_session.execute(
            select(LeaseClauseAudit).where(
                LeaseClauseAudit.lease_id == ok_lease_id,
                LeaseClauseAudit.jurisdiction == "VIC",
            )
        )
    ).scalar_one_or_none()
    assert persisted is not None


async def test_backfill_skips_unresolvable_leases(db_session, monkeypatch):
    """Leases whose property state cannot resolve are skipped, not re-enqueued forever."""
    ok_lease = await make_lease_row(db_session)
    await _set_state(db_session, ok_lease, "VIC")
    await make_lease_row(db_session)  # property state left unset
    qld_lease = await make_lease_row(db_session)
    await _set_state(db_session, qld_lease, "QLD")
    await db_session.commit()

    enqueued = []

    async def fake_enqueue(session, lease_id):
        enqueued.append(lease_id)

    monkeypatch.setattr("app.compliance_backfill.enqueue_audit", fake_enqueue)

    result = await backfill(db_session)

    assert enqueued == [ok_lease.id]
    assert result == {"enqueued": 1, "unresolvable_skipped": 2}


def test_print_report_prints_list_values_one_id_per_line(capsys):
    first, second = uuid.uuid4(), uuid.uuid4()
    _print_report({"deterministic_enqueued": 2, "missing": [first, second], "unsupported": []})
    out = capsys.readouterr().out
    assert "deterministic_enqueued: 2" in out
    assert "missing (2):" in out
    assert f"\n  {first}\n  {second}\n" in out
    assert "unsupported (0):" in out
    assert "UUID(" not in out


async def test_main_default_runs_existing_backfill(monkeypatch, capsys):
    @asynccontextmanager
    async def fake_sessionmaker():
        yield object()

    calls = []

    async def fake_backfill(session):
        calls.append(session)
        return {"enqueued": 3, "unresolvable_skipped": 2}

    monkeypatch.setattr("app.compliance_backfill.SessionLocal", lambda: fake_sessionmaker())
    monkeypatch.setattr("app.compliance_backfill.backfill", fake_backfill)

    await main([])

    assert len(calls) == 1
    assert "backfill: enqueued 3 leases, skipped 2 unresolvable" in capsys.readouterr().out


async def test_main_fix_jurisdictions_dry_run_prints_report(monkeypatch, capsys):
    @asynccontextmanager
    async def fake_sessionmaker():
        yield object()

    captured = {}

    async def fake_fix(session, execute=False):
        captured["execute"] = execute
        return {
            "deterministic_enqueued": 1,
            "clause_resubmitted": 0,
            "skipped_matching_audits": 2,
            "skipped_matching_clause": 0,
            "missing": [],
            "unsupported": [],
        }

    monkeypatch.setattr("app.compliance_backfill.SessionLocal", lambda: fake_sessionmaker())
    monkeypatch.setattr("app.compliance_backfill.fix_jurisdictions", fake_fix)

    await main(["--fix-jurisdictions"])

    assert captured["execute"] is False
    out = capsys.readouterr().out
    assert "deterministic_enqueued: 1" in out
    assert "skipped_matching_audits: 2" in out


async def test_main_fix_jurisdictions_execute_flag(monkeypatch, capsys):
    @asynccontextmanager
    async def fake_sessionmaker():
        yield object()

    captured = {}

    async def fake_fix(session, execute=False):
        captured["execute"] = execute
        return {
            "deterministic_enqueued": 0,
            "clause_resubmitted": 0,
            "skipped_matching_audits": 0,
            "skipped_matching_clause": 0,
            "missing": [],
            "unsupported": [],
        }

    monkeypatch.setattr("app.compliance_backfill.SessionLocal", lambda: fake_sessionmaker())
    monkeypatch.setattr("app.compliance_backfill.fix_jurisdictions", fake_fix)

    await main(["--fix-jurisdictions", "--execute"])

    assert captured["execute"] is True


async def test_main_execute_without_fix_jurisdictions_errors(monkeypatch, capsys):
    """--execute alone must refuse to run, not silently fall through to backfill()."""

    @asynccontextmanager
    async def fake_sessionmaker():
        yield object()

    backfill_calls = []
    fix_calls = []

    async def fake_backfill(session):
        backfill_calls.append(session)
        return 0

    async def fake_fix(session, execute=False):
        fix_calls.append(execute)
        return {}

    monkeypatch.setattr("app.compliance_backfill.SessionLocal", lambda: fake_sessionmaker())
    monkeypatch.setattr("app.compliance_backfill.backfill", fake_backfill)
    monkeypatch.setattr("app.compliance_backfill.fix_jurisdictions", fake_fix)

    with pytest.raises(SystemExit) as exc_info:
        await main(["--execute"])

    assert exc_info.value.code == 2
    assert backfill_calls == []
    assert fix_calls == []
    assert "--execute requires --fix-jurisdictions" in capsys.readouterr().err
