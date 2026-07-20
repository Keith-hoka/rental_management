import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.invitation import InvitationStatus
from app.models.organization import Role


class InvitationCreate(BaseModel):
    email: EmailStr
    # Only team members (property_manager) are invited here; tenant invites
    # arrive with leases in a later plan.
    role: Literal["property_manager"]


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: Role
    status: InvitationStatus
    expires_at: datetime


class AcceptInvitationRequest(BaseModel):
    token: str
    name: str
    password: str
