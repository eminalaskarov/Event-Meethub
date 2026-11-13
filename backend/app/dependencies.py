from collections.abc import Awaitable, Callable
from typing import Annotated

import httpx
import asyncpg
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from app.seat_realtime import SeatRealtimeHub
from app.config import settings
from app.schemas.user import UserOut
from app.security import decode_access_token

USER_COLUMNS = "id, email::text AS email, full_name, role, is_active, created_at"

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_prefix}/auth/login",
    auto_error=False,
)


def get_db_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.db_pool


DbPool = Annotated[asyncpg.Pool, Depends(get_db_pool)]

def get_realtime_hub(request: Request) -> SeatRealtimeHub:
    return request.app.state.realtime_hub


RealtimeHub = Annotated[SeatRealtimeHub, Depends(get_realtime_hub)]

def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


HttpClient = Annotated[httpx.AsyncClient, Depends(get_http_client)]
OptionalToken = Annotated[str | None, Depends(oauth2_scheme)]


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _user_from_token(pool: asyncpg.Pool, token: str) -> UserOut:
    user_id = decode_access_token(token)
    if user_id is None:
        raise _unauthorized()

    # Loading the user on each request makes deactivation take effect immediately.
    row = await pool.fetchrow(f"SELECT {USER_COLUMNS} FROM users WHERE id = $1", user_id)
    if row is None or not row["is_active"]:
        raise _unauthorized()
    return UserOut(**dict(row))


async def get_current_user(pool: DbPool, token: OptionalToken) -> UserOut:
    if token is None:
        raise _unauthorized()
    return await _user_from_token(pool, token)


async def get_optional_user(pool: DbPool, token: OptionalToken) -> UserOut | None:
    if token is None:
        return None
    return await _user_from_token(pool, token)


CurrentUser = Annotated[UserOut, Depends(get_current_user)]
OptionalUser = Annotated[UserOut | None, Depends(get_optional_user)]


def require_roles(*roles: str) -> Callable[..., Awaitable[UserOut]]:
    async def dependency(user: CurrentUser) -> UserOut:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return user

    return dependency


OrganizerUser = Annotated[UserOut, Depends(require_roles("organizer", "admin"))]