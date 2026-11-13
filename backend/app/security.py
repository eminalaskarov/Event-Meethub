from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import settings

_password_hasher = PasswordHasher()

# Verified for unknown emails so both login failures do similar work.
_DUMMY_PASSWORD_HASH = _password_hasher.hash("timing-equalization-placeholder")


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        verified = _password_hasher.verify(password_hash or _DUMMY_PASSWORD_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return verified and password_hash is not None


def create_access_token(user_id: UUID) -> tuple[str, int]:
    now = datetime.now(UTC)
    expires_in = settings.access_token_expire_minutes * 60
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_in


def decode_access_token(token: str) -> UUID | None:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
        return UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError):
        return None