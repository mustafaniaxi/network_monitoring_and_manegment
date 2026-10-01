from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from netmon.db.base import Base, TimestampMixin, str_enum
from netmon.models.enums import UserRole


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(sa.String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(sa.String(120), default="")
    hashed_password: Mapped[str] = mapped_column(sa.String(255))
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole), default=UserRole.VIEWER)
    is_active: Mapped[bool] = mapped_column(default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(default=None)

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"
