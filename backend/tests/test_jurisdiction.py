import pytest

from app.services.jurisdiction import (
    SUPPORTED_JURISDICTIONS,
    JurisdictionUnresolved,
    jurisdiction_for,
    normalize_state,
)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("NSW", "NSW"),
        ("nsw", "NSW"),
        (" New South Wales ", "NSW"),
        ("VIC", "VIC"),
        ("Vic.", "VIC"),
        ("victoria", "VIC"),
        ("Queensland", "QLD"),
        ("qld", "QLD"),
        ("South Australia", "SA"),
        ("Western Australia", "WA"),
        ("Tasmania", "TAS"),
        ("tas", "TAS"),
        ("ACT", "ACT"),
        ("Australian Capital Territory", "ACT"),
        ("Northern Territory", "NT"),
        ("nt", "NT"),
    ],
)
def test_normalize_state_aliases(text, code):
    assert normalize_state(text) == code


@pytest.mark.parametrize("text", [None, "", "  ", "Sydney", "N.S.W. Australia", "12345"])
def test_normalize_state_unrecognisable(text):
    assert normalize_state(text) is None


def test_supported_set():
    assert SUPPORTED_JURISDICTIONS == {"NSW", "VIC"}


def test_jurisdiction_for_three_reasons():
    assert jurisdiction_for("Victoria") == ("VIC", "ok")
    assert jurisdiction_for(None) == (None, "missing")
    assert jurisdiction_for("gibberish") == (None, "missing")
    assert jurisdiction_for("QLD") == (None, "unsupported")


def test_exception_carries_reason():
    exc = JurisdictionUnresolved("missing")
    assert exc.reason == "missing"
    assert isinstance(exc, Exception)


async def test_audit_rows_default_to_nsw(db_session):
    import uuid as uuid_mod
    from datetime import date

    from sqlalchemy import select, text

    from app.models import LeaseAudit
    from tests.test_lease_model import make_lease_row

    lease = await make_lease_row(db_session)
    await db_session.execute(
        text(
            "INSERT INTO lease_audits (id, lease_id, organization_id, audit_id, as_at, findings)"
            " VALUES (:id, :lease_id, :org, :audit_id, :as_at, '[]')"
        ),
        {
            "id": str(uuid_mod.uuid4()),
            "lease_id": str(lease.id),
            "org": str(lease.organization_id),
            "audit_id": str(uuid_mod.uuid4()),
            "as_at": date(2026, 8, 5),
        },
    )
    row = (
        await db_session.execute(select(LeaseAudit).where(LeaseAudit.lease_id == lease.id))
    ).scalar_one()
    assert row.jurisdiction == "NSW"
