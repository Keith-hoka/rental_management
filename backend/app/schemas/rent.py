import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.charge import ChargeInfo


class LeaseChargeGroup(BaseModel):
    """One lease's unsettled charges in a single bucket."""

    lease_id: uuid.UUID
    property_address: str
    tenant_name: str
    total: Decimal
    oldest_due: date
    charges: list[ChargeInfo]


class RentSummary(BaseModel):
    overdue: list[LeaseChargeGroup]
    upcoming: list[LeaseChargeGroup]
