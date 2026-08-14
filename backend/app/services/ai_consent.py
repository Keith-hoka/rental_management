"""Organization-level AI feature consent: append-only events, newest wins."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiFeature, AiFeatureConsent

AI_DISCLOSURE_VERSION = "2026-08-14"


async def feature_enabled(session: AsyncSession, organization_id, feature: AiFeature) -> bool:
    newest = (
        await session.execute(
            select(AiFeatureConsent.enabled)
            .where(
                AiFeatureConsent.organization_id == organization_id,
                AiFeatureConsent.feature == feature,
            )
            .order_by(AiFeatureConsent.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return bool(newest)


async def current_states(session: AsyncSession, organization_id) -> dict[AiFeature, bool]:
    return {
        feature: await feature_enabled(session, organization_id, feature) for feature in AiFeature
    }


async def record_consent(
    session: AsyncSession,
    organization_id,
    feature: AiFeature,
    enabled: bool,
    acted_by,
) -> AiFeatureConsent:
    event = AiFeatureConsent(
        organization_id=organization_id,
        feature=feature,
        enabled=enabled,
        disclosure_version=AI_DISCLOSURE_VERSION,
        acted_by=acted_by,
    )
    session.add(event)
    await session.flush()
    return event
