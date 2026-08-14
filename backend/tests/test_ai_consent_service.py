from app.models import AiFeature
from app.services.ai_consent import (
    AI_DISCLOSURE_VERSION,
    current_states,
    feature_enabled,
    record_consent,
)
from tests.test_clause_audit_service import _org_and_user
from tests.test_properties_crud import landlord_headers


async def _org(client, db_session, email):
    await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    return org_id, user_id


async def test_no_rows_means_disabled(client, db_session):
    org_id, _ = await _org(client, db_session, "consent0@example.com")
    assert await feature_enabled(db_session, org_id, AiFeature.clause_audit) is False
    states = await current_states(db_session, org_id)
    assert states == {AiFeature.clause_audit: False, AiFeature.rent_ai: False}


async def test_newest_event_wins(client, db_session):
    org_id, user_id = await _org(client, db_session, "consent1@example.com")
    await record_consent(db_session, org_id, AiFeature.clause_audit, True, user_id)
    await db_session.commit()
    assert await feature_enabled(db_session, org_id, AiFeature.clause_audit) is True
    await record_consent(db_session, org_id, AiFeature.clause_audit, False, user_id)
    await db_session.commit()
    assert await feature_enabled(db_session, org_id, AiFeature.clause_audit) is False
    states = await current_states(db_session, org_id)
    assert states[AiFeature.clause_audit] is False


async def test_event_records_version_and_actor(client, db_session):
    org_id, user_id = await _org(client, db_session, "consent2@example.com")
    event = await record_consent(db_session, org_id, AiFeature.rent_ai, True, user_id)
    await db_session.commit()
    assert event.disclosure_version == AI_DISCLOSURE_VERSION
    assert event.acted_by == user_id
    assert event.enabled is True


async def test_features_are_independent(client, db_session):
    org_id, user_id = await _org(client, db_session, "consent3@example.com")
    await record_consent(db_session, org_id, AiFeature.clause_audit, True, user_id)
    await db_session.commit()
    assert await feature_enabled(db_session, org_id, AiFeature.rent_ai) is False


async def test_same_transaction_toggle_newest_wins(client, db_session):
    org_id, user_id = await _org(client, db_session, "consent4@example.com")
    await record_consent(db_session, org_id, AiFeature.clause_audit, True, user_id)
    await record_consent(db_session, org_id, AiFeature.clause_audit, False, user_id)
    await db_session.commit()
    assert await feature_enabled(db_session, org_id, AiFeature.clause_audit) is False
