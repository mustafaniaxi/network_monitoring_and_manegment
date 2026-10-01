from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from netmon.api.deps import AdminUser, SessionDep
from netmon.core.security import hash_password
from netmon.models import User, UserRole
from netmon.schemas.user import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


async def _email_taken(session: SessionDep, email: str, exclude_id: int | None = None) -> bool:
    stmt = select(User.id).where(func.lower(User.email) == email.lower())
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    return await session.scalar(stmt) is not None


async def _active_admins(session: SessionDep) -> int:
    return int(
        await session.scalar(
            select(func.count()).where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        )
        or 0
    )


@router.get("", response_model=list[UserRead])
async def list_users(_: AdminUser, session: SessionDep) -> list[User]:
    return list((await session.scalars(select(User).order_by(User.email))).all())


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, _: AdminUser, session: SessionDep) -> User:
    if await _email_taken(session, payload.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        role=payload.role,
        is_active=payload.is_active,
        hashed_password=hash_password(payload.password),
    )
    session.add(user)
    await session.commit()
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int, payload: UserUpdate, admin: AdminUser, session: SessionDep
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    data = payload.model_dump(exclude_unset=True)
    if "email" in data and data["email"] and await _email_taken(session, data["email"], user_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    demoting = user.role == UserRole.ADMIN and (
        data.get("role", UserRole.ADMIN) != UserRole.ADMIN or data.get("is_active") is False
    )
    if demoting and await _active_admins(session) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot remove the last active administrator")
    if password := data.pop("password", None):
        user.hashed_password = hash_password(password)
    for key, value in data.items():
        if value is not None:
            setattr(user, key, value.lower() if key == "email" else value)
    await session.commit()
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, admin: AdminUser, session: SessionDep) -> None:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == admin.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot delete your own account")
    if user.role == UserRole.ADMIN and await _active_admins(session) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot delete the last administrator")
    await session.delete(user)
    await session.commit()
