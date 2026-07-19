import uuid

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import decode_token
from app.models import Membership, Role, User

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = await session.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_current_membership(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Membership:
    membership = (
        (await session.execute(select(Membership).where(Membership.user_id == user.id)))
        .scalars()
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="No organization membership")
    return membership


def require_roles(*roles: Role):
    """Dependency factory: 403 unless the current membership has one of the roles."""

    async def checker(membership: Membership = Depends(get_current_membership)) -> Membership:
        if membership.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return membership

    return checker
