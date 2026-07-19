import hashlib
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def password_fingerprint(hashed_password: str | None) -> str:
    """Short, non-reversible marker of the current password.

    Embedded in reset tokens so a token stops validating once the password
    changes, making each reset link single-use.
    """
    return hashlib.sha256((hashed_password or "").encode()).hexdigest()[:16]


def create_token(subject: str, token_type: str, expires_delta: timedelta) -> str:
    """Create a signed JWT. token_type is 'access', 'refresh', or 'reset'."""
    payload = {
        "sub": subject,
        "type": token_type,
        "exp": datetime.now(UTC) + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_reset_token(email: str, hashed_password: str | None, expires_delta: timedelta) -> str:
    """Create a single-use password reset token bound to the current password."""
    payload = {
        "sub": email,
        "type": "reset",
        "pwfp": password_fingerprint(hashed_password),
        "exp": datetime.now(UTC) + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises jwt.PyJWTError on invalid tokens."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
