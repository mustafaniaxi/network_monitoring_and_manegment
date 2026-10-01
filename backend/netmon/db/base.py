"""Declarative base, naming conventions and portable column types."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC datetimes on every backend.

    PostgreSQL stores ``timestamptz``; SQLite has no timezone support so values are stored as
    naive UTC and re-attached to UTC on load. Application code therefore only ever sees aware
    datetimes.
    """

    impl = sa.DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        if dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Counter(TypeDecorator[int]):
    """Unsigned 64-bit SNMP counter stored losslessly as text (exceeds signed BIGINT)."""

    impl = sa.String(24)
    cache_ok = True

    def process_bind_param(self, value: int | None, dialect: Dialect) -> str | None:
        return None if value is None else str(int(value))

    def process_result_value(self, value: str | None, dialect: Dialect) -> int | None:
        return None if value is None else int(value)


def str_enum(enum_cls: type[StrEnum], length: int = 32) -> sa.Enum:
    """Store enums as plain strings (portable, no PostgreSQL ENUM migrations)."""
    return sa.Enum(
        enum_cls,
        native_enum=False,
        create_constraint=False,
        length=length,
        values_callable=lambda members: [m.value for m in members],
    )


class Base(DeclarativeBase):
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: dict[Any, Any] = {datetime: UTCDateTime()}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )
