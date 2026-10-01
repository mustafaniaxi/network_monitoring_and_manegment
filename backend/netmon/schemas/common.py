from __future__ import annotations

import ipaddress
import re
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*\.?$"
)


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=False)


T = TypeVar("T")


class Page(Schema, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class Message(Schema):
    detail: str


def validate_host(value: str) -> str:
    """Accept an IPv4/IPv6 address or a DNS hostname."""
    value = value.strip()
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    if _HOSTNAME_RE.match(value) and not value.replace(".", "").isdigit():
        return value.lower()
    raise ValueError("must be a valid IPv4/IPv6 address or hostname")
