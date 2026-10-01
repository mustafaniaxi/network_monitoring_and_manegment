from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select

from netmon.api.deps import CurrentUser, SessionDep, SettingsDep, password_version
from netmon.core.security import (
    LoginThrottle,
    create_access_token,
    hash_password,
    verify_password,
)
from netmon.db.base import utcnow
from netmon.models import User
from netmon.schemas.common import Message
from netmon.schemas.user import PasswordChange, ProfileUpdate, TokenResponse, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])

# Constant-time-ish defence: verify against a dummy hash when the user does not exist.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


@router.post("/login", response_model=TokenResponse, summary="Obtain an access token")
async def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
    settings: SettingsDep,
) -> TokenResponse:
    throttle: LoginThrottle = request.app.state.login_throttle
    client = request.client.host if request.client else "unknown"
    key = f"{client}:{form.username.lower()}"
    if throttle.is_locked(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed login attempts, try again later",
            headers={"Retry-After": str(throttle.retry_after(key))},
        )

    user = await session.scalar(
        select(User).where(func.lower(User.email) == form.username.strip().lower())
    )
    valid = verify_password(form.password, user.hashed_password if user else _DUMMY_HASH)
    if user is None or not valid or not user.is_active:
        throttle.register_failure(key)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    throttle.reset(key)
    user.last_login_at = utcnow()
    await session.commit()
    token = create_access_token(
        settings, str(user.id), {"role": user.role.value, "pv": password_version(user)}
    )
    return TokenResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserRead.model_validate(user),
    )


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserRead)
async def update_profile(payload: ProfileUpdate, user: CurrentUser, session: SessionDep) -> User:
    db_user = await session.get(User, user.id)
    assert db_user is not None
    db_user.full_name = payload.full_name
    await session.commit()
    return db_user


@router.post("/change-password", response_model=Message)
async def change_password(
    payload: PasswordChange, user: CurrentUser, session: SessionDep
) -> Message:
    db_user = await session.get(User, user.id)
    assert db_user is not None
    if not verify_password(payload.current_password, db_user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    db_user.hashed_password = hash_password(payload.new_password)
    await session.commit()
    return Message(detail="Password changed; please sign in again")
