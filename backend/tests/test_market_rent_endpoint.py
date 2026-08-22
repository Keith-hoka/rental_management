import uuid

import httpx

from app.services import compliance
from tests.test_leases import lease_body
from tests.test_properties_crud import landlord_headers

SERVICE_BODY = {
    "jurisdiction": "NSW",
    "area": "2000",
    "area_label": "2000",
    "dwelling_type": "unit",
    "bedrooms": 2,
    "estimate_weekly": "760",
    "band": {"low": "698", "high": "886"},
    "basis": "median",
    "period": "2026-07",
    "period_end": "2026-07-31",
    "stale": False,
    "sample_size": 170,
    "fallback": None,
    "series": [],
    "trend": {"from_period": "2025-07", "from_median": "700.00", "change_pct": "8.6"},
    "source": {
        "name": "NSW Fair Trading rental bond lodgements",
        "url": "https://www.nsw.gov.au/housing-and-construction/rental-forms-surveys-and-data/rental-bond-data",
        "licence": "NSW Government open data (terms on the source page)",
    },
    "disclaimer": "General information, not legal advice.",
}

EMPTY_BODY = {
    **SERVICE_BODY,
    "area_label": None,
    "estimate_weekly": None,
    "band": None,
    "period": None,
    "period_end": None,
    "sample_size": None,
    "trend": None,
}


async def _property(
    client,
    email,
    state="NSW",
    postcode="2000",
    city=None,
    ptype="apartment",
    bedrooms=2,
    with_lease=True,
):
    headers = await landlord_headers(client, email)
    prop = (
        await client.post(
            "/api/v1/properties",
            json={
                "address": "7 Market St",
                "state": state,
                "postcode": postcode,
                "city": city,
                "type": ptype,
                "bedrooms": bedrooms,
            },
            headers=headers,
        )
    ).json()
    if with_lease:
        await client.post(
            f"/api/v1/properties/{prop['id']}/leases",
            json=lease_body(start_date="2026-01-01", end_date="2027-12-31"),
            headers=headers,
        )
    return headers, uuid.UUID(prop["id"])


def _fake_get(monkeypatch, captured, response=None, raises=None):
    async def _fake(params):
        captured.append(params)
        if raises is not None:
            raise raises
        return dict(response or SERVICE_BODY)

    monkeypatch.setattr("app.services.compliance.get_market_rent", _fake)
    monkeypatch.setattr(compliance.settings, "compliance_api_url", "http://service")
    monkeypatch.setattr(compliance.settings, "compliance_api_key", "k")


async def test_requires_auth(client, db_session):
    _, property_id = await _property(client, "mr401@example.com")
    response = await client.get(f"/api/v1/properties/{property_id}/market-rent")
    assert response.status_code == 401


async def test_missing_postcode_is_422(client, db_session, monkeypatch):
    _fake_get(monkeypatch, [])
    headers, property_id = await _property(client, "mrnopc@example.com", postcode=None)
    response = await client.get(f"/api/v1/properties/{property_id}/market-rent", headers=headers)
    assert response.status_code == 422


async def test_returns_market_with_current_rent_gap(client, db_session, monkeypatch):
    captured = []
    _fake_get(monkeypatch, captured)
    headers, property_id = await _property(client, "mr200@example.com")
    response = await client.get(f"/api/v1/properties/{property_id}/market-rent", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["market"] == SERVICE_BODY
    assert body["current_weekly"] == "346"
    assert body["gap_pct"] == "-54.5"
    assert captured == [
        {"jurisdiction": "NSW", "area": "2000", "dwelling_type": "unit", "bedrooms": 2}
    ]


async def test_vacant_property_has_null_gap(client, db_session, monkeypatch):
    _fake_get(monkeypatch, [])
    headers, property_id = await _property(client, "mrvacant@example.com", with_lease=False)
    body = (
        await client.get(f"/api/v1/properties/{property_id}/market-rent", headers=headers)
    ).json()
    assert body["current_weekly"] is None and body["gap_pct"] is None


async def test_no_estimate_has_null_gap(client, db_session, monkeypatch):
    _fake_get(monkeypatch, [], response=EMPTY_BODY)
    headers, property_id = await _property(client, "mrempty@example.com")
    body = (
        await client.get(f"/api/v1/properties/{property_id}/market-rent", headers=headers)
    ).json()
    assert body["current_weekly"] == "346" and body["gap_pct"] is None


async def test_vic_uses_city_and_unresolved_state_is_422(client, db_session, monkeypatch):
    captured = []
    _fake_get(monkeypatch, captured)
    headers, property_id = await _property(
        client, "mrvic@example.com", state="VIC", postcode=None, city="Albert Park"
    )
    await client.get(f"/api/v1/properties/{property_id}/market-rent", headers=headers)
    assert captured[0]["area"] == "Albert Park" and captured[0]["jurisdiction"] == "VIC"
    headers, property_id = await _property(client, "mrnostate@example.com", state=None)
    response = await client.get(f"/api/v1/properties/{property_id}/market-rent", headers=headers)
    assert response.status_code == 422


async def test_service_error_is_502_and_disabled_is_503(client, db_session, monkeypatch):
    _fake_get(monkeypatch, [], raises=httpx.ConnectError("down"))
    headers, property_id = await _property(client, "mr502@example.com")
    assert (
        await client.get(f"/api/v1/properties/{property_id}/market-rent", headers=headers)
    ).status_code == 502
    monkeypatch.setattr(compliance.settings, "compliance_api_url", "")
    assert (
        await client.get(f"/api/v1/properties/{property_id}/market-rent", headers=headers)
    ).status_code == 503
