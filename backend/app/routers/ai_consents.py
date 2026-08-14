from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_membership, require_roles
from app.models import AiFeature, Membership, Role
from app.schemas.ai_consent import AiConsentState, AiConsentToggle
from app.services.ai_consent import AI_DISCLOSURE_VERSION, current_states, record_consent

router = APIRouter(prefix="/api", tags=["ai-consents"])

landlord_only = require_roles(Role.landlord)


async def _state(session: AsyncSession, organization_id) -> AiConsentState:
    states = await current_states(session, organization_id)
    return AiConsentState(
        features={feature.value: enabled for feature, enabled in states.items()},
        disclosure_version=AI_DISCLOSURE_VERSION,
    )


@router.get("/ai-consents", response_model=AiConsentState)
async def get_ai_consents(
    membership: Membership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_session),
) -> AiConsentState:
    return await _state(session, membership.organization_id)


@router.post("/ai-consents/{feature}", response_model=AiConsentState)
async def set_ai_consent(
    feature: AiFeature,
    body: AiConsentToggle,
    membership: Membership = Depends(landlord_only),
    session: AsyncSession = Depends(get_session),
) -> AiConsentState:
    await record_consent(
        session, membership.organization_id, feature, body.enabled, membership.user_id
    )
    await session.commit()
    return await _state(session, membership.organization_id)
