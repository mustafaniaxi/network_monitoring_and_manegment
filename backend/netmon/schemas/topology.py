from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from netmon.models import DeviceStatus, DeviceType, LinkType
from netmon.schemas.common import Schema


class LinkBase(Schema):
    link_type: LinkType = LinkType.ETHERNET
    source_interface: str | None = Field(default=None, max_length=64)
    target_interface: str | None = Field(default=None, max_length=64)
    bandwidth_mbps: float | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=255)


class LinkCreate(LinkBase):
    source_id: int
    target_id: int

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        if self.source_id == self.target_id:
            raise ValueError("a link must connect two different devices")
        return self


class LinkUpdate(Schema):
    link_type: LinkType | None = None
    source_interface: str | None = Field(default=None, max_length=64)
    target_interface: str | None = Field(default=None, max_length=64)
    bandwidth_mbps: float | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=255)


class LinkRead(LinkBase):
    id: int
    source_id: int
    target_id: int


class TopologyNode(Schema):
    id: int
    name: str
    ip_address: str
    device_type: DeviceType
    status: DeviceStatus
    is_monitored: bool
    last_latency_ms: float | None
    x: float | None
    y: float | None


class TopologyEdge(LinkRead):
    status: Literal["up", "down", "degraded", "unknown"]


class Topology(Schema):
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]


class NodePosition(Schema):
    device_id: int
    x: float
    y: float
