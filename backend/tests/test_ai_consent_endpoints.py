from app.models import AiFeature
from app.services.ai_consent import AI_DISCLOSURE_VERSION, record_consent
from tests.test_invitation_accept import create_invite
from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers


async def enable_clause_audit(db_session, org_id, user_id):
    """Test helper: consent an organization to clause audits."""
    await record_consent(db_session, org_id, AiFeature.clause_audit, True, user_id)
    await db_session.commit()


async def test_get_defaults_all_off(client, db_session):
    headers = await landlord_headers(client, "aic1@example.com")
    response = await client.get("/api/ai-consents", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["features"] == {"clause_audit": False, "rent_ai": False}
    assert body["disclosure_version"] == AI_DISCLOSURE_VERSION


async def test_landlord_toggles_feature(client, db_session):
    headers = await landlord_headers(client, "aic2@example.com")
    response = await client.post(
        "/api/ai-consents/clause_audit", json={"enabled": True}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["features"]["clause_audit"] is True

    response = await client.post(
        "/api/ai-consents/clause_audit", json={"enabled": False}, headers=headers
    )
    assert response.json()["features"]["clause_audit"] is False


async def test_non_landlord_cannot_toggle(client, db_session):
    headers = await landlord_headers(client, "aic3@example.com")
    lease_id = await make_lease(client, headers, "3 Consent St")
    tenant_headers = await onboard_tenant(
        client, db_session, headers, lease_id, "aictenant@example.com"
    )
    response = await client.post(
        "/api/ai-consents/clause_audit", json={"enabled": True}, headers=tenant_headers
    )
    assert response.status_code == 403


async def test_property_manager_cannot_toggle(client, db_session):
    headers = await landlord_headers(client, "aic5@example.com")
    token = await create_invite(client, db_session, headers, email="aic5pm@example.com")
    accepted = await client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "name": "PM", "password": "pmsecret1"},
    )
    pm_headers = {"Authorization": f"Bearer {accepted.json()['access_token']}"}
    response = await client.post(
        "/api/ai-consents/clause_audit", json={"enabled": True}, headers=pm_headers
    )
    assert response.status_code == 403


async def test_unknown_feature_is_422(client, db_session):
    headers = await landlord_headers(client, "aic4@example.com")
    response = await client.post(
        "/api/ai-consents/toaster", json={"enabled": True}, headers=headers
    )
    assert response.status_code == 422
