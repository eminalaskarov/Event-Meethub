from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordRequestForm

from app.dependencies import USER_COLUMNS, CurrentUser, DbPool
from app.schemas.user import TokenOut, UserOut, UserRegister
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, pool: DbPool):
    password_hash = await run_in_threadpool(hash_password, payload.password)

    try:
        row = await pool.fetchrow(
            f"""
            INSERT INTO users (email, password_hash, full_name, role)
            VALUES ($1::text::citext, $2, $3, $4::user_role)
            RETURNING {USER_COLUMNS}
            """,
            payload.email,
            password_hash,
            payload.full_name,
            payload.account_type,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc

    return dict(row)


@router.post("/login", response_model=TokenOut)
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], pool: DbPool):
    """Use the email address as the OAuth2 `username` field."""
    row = await pool.fetchrow(
        "SELECT id, password_hash, is_active FROM users WHERE email = $1::text::citext",
        form.username,
    )

    password_hash = row["password_hash"] if row else None
    password_ok = await run_in_threadpool(verify_password, form.password, password_hash)

    if row is None or not password_ok or not row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token, expires_in = create_access_token(row["id"])
    return {"access_token": token, "expires_in": expires_in}


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user