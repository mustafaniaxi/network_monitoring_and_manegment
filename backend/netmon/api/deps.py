"""FastAPI dependencies: settings, DB session, authentication and role checks."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from netmon.core.config import Settings
from netmon.core.security import TokenError, decode_access_token
from netmon.models import User, UserRole
from netmon.services.discovery import DiscoveryManager
from netmon.services.events import EventHub
from netmon.services.monitoring.service import MonitoringService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# Starlette renamed HTTP_422_UNPROCESSABLE_ENTITY -> _CONTENT; a literal works with both.
UNPROCESSABLE = 422


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


def get_monitor(request: Request) -> MonitoringService:
    monitor: MonitoringService = request.app.state.monitor
    return monitor


def get_discovery(request: Request) -> DiscoveryManager:
    discovery: DiscoveryManager = request.app.state.discovery
    return discovery


def get_hub(request: Request) -> EventHub:
    hub: EventHub = request.app.state.hub
    return hub


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
MonitorDep = Annotated[MonitoringService, Depends(get_monitor)]
DiscoveryDep = Annotated[DiscoveryManager, Depends(get_discovery)]

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def password_version(user: User) -> str:
    """Short fingerprint of the password hash; changing the password invalidates old tokens."""
    return user.hashed_password[-10:]


async def authenticate_token(session: AsyncSession, settings: Settings, token: str) -> User:
    try:
        payload = decode_access_token(settings, token)
        user_id = int(payload["sub"])
    except (TokenError, ValueError, KeyError):
        raise _UNAUTHORIZED from None
    user = await session.get(User, user_id)
    if user is None or not user.is_active or payload.get("pv") != password_version(user):
        raise _UNAUTHORIZED
    return user


async def get_current_user(
    session: SessionDep,
    settings: SettingsDep,
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> User:
    if not token:
        raise _UNAUTHORIZED
    return await authenticate_token(session, settings, token)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[..., Coroutine[Any, Any, User]]:
    async def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {' or '.join(r.value for r in roles)}",
            )
        return user

    return checker


OperatorUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))]
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


def pagination(page: int = 1, page_size: int = 50) -> tuple[int, int]:
    if page < 1:
        raise HTTPException(UNPROCESSABLE, "page must be >= 1")
    if not 1 <= page_size <= 500:
        raise HTTPException(UNPROCESSABLE, "page_size must be 1..500")
    return page, page_size


PaginationDep = Annotated[tuple[int, int], Depends(pagination)]
