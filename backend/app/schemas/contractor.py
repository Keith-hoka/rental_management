import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class ContractorCreate(BaseModel):
    name: str
    trade: str | None = None
    phone: str | None = None
    email: EmailStr | None = None


class ContractorUpdate(BaseModel):
    name: str | None = None
    trade: str | None = None
    phone: str | None = None
    email: EmailStr | None = None


class ContractorInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    trade: str | None
    phone: str | None
    email: EmailStr | None
    created_at: datetime


class AssignContractor(BaseModel):
    contractor_id: uuid.UUID
