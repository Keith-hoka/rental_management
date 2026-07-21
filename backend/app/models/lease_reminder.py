import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class LeaseReminder(Base):
    __tablename__ = "lease_reminders"
    __table_args__ = (UniqueConstraint("lease_id", "threshold_days"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lease_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leases.id", ondelete="CASCADE"), index=True
    )
    threshold_days: Mapped[int] = mapped_column()
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
