import uuid

import httpx
import pytest

from app.services import compliance
from tests.test_clause_audit_service import _org_and_user
from tests.test_leases import lease_body
from tests.test_properties_crud import landlord_headers

BODY = {"renewal_start": "2027-01-01"}

CANNED_RESPONSE = {
    "current_weekly": "600",
    "suggested_weekly": "630",
    "range": {"low": "600", "high": "690"},
    "market_gap": "within",
    "market": {
        "period": "2026-07",
        "median": "760",
        "p25": "698",
        "p75": "886",
        "sample_size": 170,
        "fallback": None,
        "source": {
            "name": "NSW Fair Trading rental bond lodgements",
            "url": "https://www.nsw.gov.au/housing-and-construction/rental-forms-surveys-and-data/rental-bond-data",
            "licence": "NSW Government open data (terms on the source page)",
        },
    },
    "law_card": [
        {
            "rule_id": "nsw.rent_increase_frequency",
            "verdict": "green",
            "summary": "Rent last increased more than 12 months before this renewal.",
            "evidence": {},
            "citations": [
                {
                    "act": "Residential Tenancies Act 2010 (NSW)",
                    "section_no": "41",
                    "as_at": "2026-08-06",
                    "section_id": "00000000-0000-0000-0000-000000000000",
                    "label": None,
                }
            ],
            "skip_reason": None,
        }
    ],
    "law_blocked": False,
    "reasoning": "Median 760 supports 630.",
    "model": "claude-sonnet-5",
    "engine_version": "1.6.0",
    "disclaimer": "General information, not legal advice.",
}


async def _setup(
    client,
    db_session,
    email,
    address,
    state="NSW",
    consent=True,
    postcode="2000",
    city=None,
    bedrooms=2,
    ptype="house",
):
    """Create a landlord with a property (state/postcode/city/type/bedrooms) and one lease."""
    from tests.test_ai_consent_endpoints import enable_rent_ai

    headers = await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    created_property = (
        await client.post(
            "/api/v1/properties",
            json={
                "address": address,
                "state": state,
                "postcode": postcode,
                "city": city,
                "type": ptype,
                "bedrooms": bedrooms,
            },
            headers=headers,
        )
    ).json()
    lease = (
        await client.post(
            f"/api/v1/properties/{created_property['id']}/leases",
            json=lease_body(),
            headers=headers,
        )
    ).json()
    lease_id = uuid.UUID(lease["id"])
    if consent:
        await enable_rent_ai(db_session, org_id, user_id)
    return headers, lease_id


def _fake_create(monkeypatch, captured, response=None, raises=None):
    async def _fake(payload):
        captured.append(payload)
        if raises is not None:
            raise raises
        return dict(response or CANNED_RESPONSE)

    monkeypatch.setattr("app.services.compliance.create_rent_suggestion", _fake)


async def test_post_requires_auth(client, db_session):
    _, lease_id = await _setup(client, db_session, "rs401@example.com", "1 Suggest St")
    response = await client.post(f"/api/v1/leases/{lease_id}/rent-suggestion", json=BODY)
    assert response.status_code == 401


async def test_post_disabled_is_503(client, db_session):
    headers, lease_id = await _setup(client, db_session, "rs503@example.com", "2 Suggest St")
    response = await client.post(
        f"/api/v1/leases/{lease_id}/rent-suggestion", json=BODY, headers=headers
    )
    assert response.status_code == 503


async def test_post_without_consent_is_403(client, db_session, compliance_on):
    headers, lease_id = await _setup(
        client, db_session, "rs403@example.com", "3 Suggest St", consent=False
    )
    response = await client.post(
        f"/api/v1/leases/{lease_id}/rent-suggestion", json=BODY, headers=headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == {"code": "ai_consent_required", "feature": "rent_ai"}


async def test_post_tenant_role_is_403(client, db_session, compliance_on):
    from tests.test_portal import onboard_tenant

    headers, lease_id = await _setup(client, db_session, "rsrole@example.com", "4 Suggest St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "rsrole-t@example.com")
    response = await client.post(
        f"/api/v1/leases/{lease_id}/rent-suggestion", json=BODY, headers=tenant
    )
    assert response.status_code == 403


async def test_post_foreign_lease_is_404(client, db_session, compliance_on):
    _, lease_id = await _setup(client, db_session, "rsown@example.com", "5 Suggest St")
    # A second, consented org: without its own consent, the AI-consent gate (which
    # runs before the ownership lookup) would 403 first and never prove the 404.
    other_headers, _ = await _setup(client, db_session, "rsother@example.com", "5b Other St")
    response = await client.post(
        f"/api/v1/leases/{lease_id}/rent-suggestion", json=BODY, headers=other_headers
    )
    assert response.status_code == 404


async def test_post_returns_422_when_state_missing(client, db_session, compliance_on):
    headers, lease_id = await _setup(
        client, db_session, "rsstate@example.com", "6 Suggest St", state=None
    )
    response = await client.post(
        f"/api/v1/leases/{lease_id}/rent-suggestion", json=BODY, headers=headers
    )
    assert response.status_code == 422


async def test_post_sends_expected_payload_and_returns_service_response(
    client, db_session, compliance_on, monkeypatch
):
    headers, lease_id = await _setup(
        client,
        db_session,
        "rspayload@example.com",
        "7 Suggest St",
        postcode="2010",
        bedrooms=3,
        ptype="house",
    )
    captured = []
    _fake_create(monkeypatch, captured)

    response = await client.post(
        f"/api/v1/leases/{lease_id}/rent-suggestion", json=BODY, headers=headers
    )

    assert response.status_code == 200
    assert response.json() == CANNED_RESPONSE
    assert len(captured) == 1
    payload = captured[0]
    assert payload["jurisdiction"] == "NSW"
    assert payload["property"] == {"area_key": "2010", "dwelling_type": "house", "bedrooms": 3}
    assert payload["renewal_start"] == "2027-01-01"
    # Numeric(10, 2) columns round-trip through Postgres with two decimal
    # places, unlike the in-memory Decimal("1500") lease_body() was built from.
    assert payload["lease"]["rent_amount"] == "1500.00"
    assert payload["lease"]["rent_frequency"] == "monthly"
    assert payload["lease"]["start_date"] == "2026-01-01"
    assert payload["lease"]["end_date"] == "2026-12-31"
    assert payload["lease"]["bond_amount"] == "3000.00"


async def test_post_vic_uses_city_as_area_key(client, db_session, compliance_on, monkeypatch):
    headers, lease_id = await _setup(
        client,
        db_session,
        "rsvic@example.com",
        "8 Suggest St",
        state="VIC",
        city="Richmond",
        postcode="3121",
    )
    captured = []
    _fake_create(monkeypatch, captured)

    response = await client.post(
        f"/api/v1/leases/{lease_id}/rent-suggestion", json=BODY, headers=headers
    )

    assert response.status_code == 200
    assert captured[0]["jurisdiction"] == "VIC"
    assert captured[0]["property"]["area_key"] == "Richmond"


@pytest.mark.parametrize(
    ("ptype", "expected"),
    [
        ("house", "house"),
        ("townhouse", "townhouse"),
        ("other", "other"),
        ("apartment", "unit"),
        ("condo", "unit"),
    ],
)
async def test_post_maps_dwelling_type(
    client, db_session, compliance_on, monkeypatch, ptype, expected
):
    headers, lease_id = await _setup(
        client, db_session, f"rsdwell-{ptype}@example.com", "9 Suggest St", ptype=ptype
    )
    captured = []
    _fake_create(monkeypatch, captured)

    response = await client.post(
        f"/api/v1/leases/{lease_id}/rent-suggestion", json=BODY, headers=headers
    )

    assert response.status_code == 200
    assert captured[0]["property"]["dwelling_type"] == expected


async def test_post_service_502_is_passthrough(client, db_session, compliance_on, monkeypatch):
    headers, lease_id = await _setup(client, db_session, "rs502@example.com", "10 Suggest St")
    request = httpx.Request("POST", "http://service/v1/rent-suggestions")
    bad_gateway = httpx.Response(502, request=request)
    error = httpx.HTTPStatusError("bad gateway", request=request, response=bad_gateway)
    captured = []
    _fake_create(monkeypatch, captured, raises=error)

    response = await client.post(
        f"/api/v1/leases/{lease_id}/rent-suggestion", json=BODY, headers=headers
    )

    assert response.status_code == 502
    assert response.json()["detail"] == {"code": "judge_unavailable"}


async def test_post_service_timeout_is_504(client, db_session, compliance_on, monkeypatch):
    headers, lease_id = await _setup(client, db_session, "rs504@example.com", "11 Suggest St")
    request = httpx.Request("POST", "http://service/v1/rent-suggestions")
    error = httpx.TimeoutException("timed out", request=request)
    captured = []
    _fake_create(monkeypatch, captured, raises=error)

    response = await client.post(
        f"/api/v1/leases/{lease_id}/rent-suggestion", json=BODY, headers=headers
    )

    assert response.status_code == 504
    assert response.json()["detail"] == {"code": "judge_timeout"}


async def test_create_rent_suggestion_uses_dedicated_timeout(compliance_on, monkeypatch):
    """Rent suggestions get their own (longer) timeout, independent of TIMEOUT."""
    captured = {}

    class _FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def post(self, url, **kwargs):
            return _FakeResponse()

    monkeypatch.setattr("app.services.compliance.httpx.AsyncClient", _FakeAsyncClient)

    await compliance.create_rent_suggestion({})

    assert captured["timeout"] == compliance.RENT_SUGGESTION_TIMEOUT
    assert compliance.RENT_SUGGESTION_TIMEOUT != compliance.TIMEOUT
