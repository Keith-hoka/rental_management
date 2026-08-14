import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AiFeature(str, enum.Enum):
    clause_audit = "clause_audit"
    rent_ai = "rent_ai"


class AiFeatureConsent(Base):
    """Append-only consent events; the newest row per feature is the state."""

    __tablename__ = "ai_feature_consents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    feature: Mapped[AiFeature] = mapped_column(Enum(AiFeature))
    enabled: Mapped[bool] = mapped_column()
    disclosure_version: Mapped[str] = mapped_column(String(20))
    acted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
