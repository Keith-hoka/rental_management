from datetime import timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.deps import get_current_membership, get_current_user
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.models import Membership, Organization, Role, User
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    RefreshRequest,
    SignupRequest,
    TokenPair,
)

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


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    """Exchange email + password for a token pair."""
    user = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()
    if (
        not user
        or not user.hashed_password
        or not verify_password(body.password, user.hashed_password)
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return issue_tokens(str(user.id))


@router.get("/me", response_model=MeResponse)
async def me(
    user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_membership),
) -> MeResponse:
    """Return the authenticated user's profile and role."""
    return MeResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=membership.role.value,
        organization_id=membership.organization_id,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest) -> TokenPair:
    """Exchange a valid refresh token for a new token pair."""
    try:
        payload = decode_token(body.refresh_token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    return issue_tokens(payload["sub"])
