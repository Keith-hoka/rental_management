from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.security import create_token, hash_password
from app.models import Membership, Organization, Role, User
from app.schemas.auth import SignupRequest, TokenPair

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def issue_tokens(user_id: str) -> TokenPair:
    return TokenPair(
        access_token=create_token(
            user_id, "access", timedelta(minutes=settings.access_token_minutes)
        ),
        refresh_token=create_token(user_id, "refresh", timedelta(days=settings.refresh_token_days)),
    )


@router.post("/signup", status_code=201, response_model=TokenPair)
async def signup(body: SignupRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    """Create a landlord account with its organization."""
    existing = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(email=body.email, hashed_password=hash_password(body.password), name=body.name)
    org = Organization(name=body.organization_name)
    session.add_all([user, org])
    await session.flush()
    session.add(Membership(user_id=user.id, organization_id=org.id, role=Role.landlord))
    await session.commit()
    return issue_tokens(str(user.id))
