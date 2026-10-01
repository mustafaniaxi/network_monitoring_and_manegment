"""SNMP collector (v1 / v2c / v3) built on pysnmp's asyncio API.

Collected data:
* SNMPv2-MIB system group: sysDescr, sysObjectID, sysUpTime, sysName
* CPU: HOST-RESOURCES-MIB ``hrProcessorLoad`` (avg over cores), fallback UCD ``ssCpuIdle``
* Memory: UCD-SNMP-MIB ``memTotalReal/memAvailReal``, fallback HOST-RESOURCES ``hrStorageRam``
* Interfaces: IF-MIB ``ifTable`` + ``ifXTable`` (64-bit HC counters when available)
"""

from __future__ import annotations

import logging
from typing import Any

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    EndOfMibView,
    NoSuchInstance,
    NoSuchObject,
    ObjectIdentity,
    ObjectType,
    OctetString,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    bulk_walk_cmd,
    get_cmd,
    usmAesCfb128Protocol,
    usmAesCfb256Protocol,
    usmDESPrivProtocol,
    usmHMAC192SHA256AuthProtocol,
    usmHMAC384SHA512AuthProtocol,
    usmHMACMD5AuthProtocol,
    usmHMACSHAAuthProtocol,
    usmNoAuthProtocol,
    usmNoPrivProtocol,
    walk_cmd,
)

from netmon.models import SnmpAuthProtocol, SnmpPrivProtocol, SnmpVersion
from netmon.services.monitoring.types import InterfaceCounters, SnmpCredentials, SnmpSnapshot

log = logging.getLogger(__name__)

# SNMPv2-MIB
SYS_DESCR = "1.3.6.1.2.1.1.1.0"
SYS_OBJECT_ID = "1.3.6.1.2.1.1.2.0"
SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
SYS_NAME = "1.3.6.1.2.1.1.5.0"
# UCD-SNMP-MIB (net-snmp agents)
UCD_MEM_TOTAL = "1.3.6.1.4.1.2021.4.5.0"
UCD_MEM_AVAIL = "1.3.6.1.4.1.2021.4.6.0"
UCD_MEM_BUFFER = "1.3.6.1.4.1.2021.4.14.0"
UCD_MEM_CACHED = "1.3.6.1.4.1.2021.4.15.0"
UCD_CPU_IDLE = "1.3.6.1.4.1.2021.11.11.0"
# HOST-RESOURCES-MIB
HR_PROCESSOR_LOAD = "1.3.6.1.2.1.25.3.3.1.2"
HR_STORAGE_TYPE = "1.3.6.1.2.1.25.2.3.1.2"
HR_STORAGE_UNITS = "1.3.6.1.2.1.25.2.3.1.4"
HR_STORAGE_SIZE = "1.3.6.1.2.1.25.2.3.1.5"
HR_STORAGE_USED = "1.3.6.1.2.1.25.2.3.1.6"
HR_STORAGE_RAM = "1.3.6.1.2.1.25.2.1.2"
# IF-MIB
IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
IF_TYPE = "1.3.6.1.2.1.2.2.1.3"
IF_SPEED = "1.3.6.1.2.1.2.2.1.5"
IF_ADMIN_STATUS = "1.3.6.1.2.1.2.2.1.7"
IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"
IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"
IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"
IF_NAME = "1.3.6.1.2.1.31.1.1.1.1"
IF_HC_IN_OCTETS = "1.3.6.1.2.1.31.1.1.1.6"
IF_HC_OUT_OCTETS = "1.3.6.1.2.1.31.1.1.1.10"
IF_HIGH_SPEED = "1.3.6.1.2.1.31.1.1.1.15"
IF_ALIAS = "1.3.6.1.2.1.31.1.1.1.18"

_IF_STATUS = {1: "up", 2: "down", 3: "testing", 4: "unknown", 5: "dormant", 6: "notPresent",
              7: "lowerLayerDown"}  # fmt: skip

_AUTH_PROTOCOLS = {
    SnmpAuthProtocol.NONE: usmNoAuthProtocol,
    SnmpAuthProtocol.MD5: usmHMACMD5AuthProtocol,
    SnmpAuthProtocol.SHA: usmHMACSHAAuthProtocol,
    SnmpAuthProtocol.SHA256: usmHMAC192SHA256AuthProtocol,
    SnmpAuthProtocol.SHA512: usmHMAC384SHA512AuthProtocol,
}
_PRIV_PROTOCOLS = {
    SnmpPrivProtocol.NONE: usmNoPrivProtocol,
    SnmpPrivProtocol.DES: usmDESPrivProtocol,
    SnmpPrivProtocol.AES128: usmAesCfb128Protocol,
    SnmpPrivProtocol.AES256: usmAesCfb256Protocol,
}

MAX_INTERFACES = 512


class SnmpError(Exception):
    pass


def _convert(value: Any) -> Any:
    """Turn a pysnmp value into a plain Python value (None for 'no such object')."""
    if isinstance(value, NoSuchObject | NoSuchInstance | EndOfMibView):
        return None
    if isinstance(value, OctetString):
        raw = bytes(value)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.hex(":")
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value)


class SnmpClient:
    def __init__(self, timeout: float = 2.0, retries: int = 1) -> None:
        self.timeout = timeout
        self.retries = retries
        self._engine: SnmpEngine | None = None

    @property
    def engine(self) -> SnmpEngine:
        if self._engine is None:  # lazily created inside the running event loop
            self._engine = SnmpEngine()
        return self._engine

    def close(self) -> None:
        if self._engine is not None:
            self._engine.close_dispatcher()
            self._engine = None

    # ------------------------------------------------------------------ low level
    @staticmethod
    def _auth(creds: SnmpCredentials) -> CommunityData | UsmUserData:
        if creds.version == SnmpVersion.V3:
            if not creds.v3_username:
                raise SnmpError("SNMPv3 requires a username")
            return UsmUserData(
                creds.v3_username,
                authKey=creds.v3_auth_key or None,
                privKey=creds.v3_priv_key or None,
                authProtocol=_AUTH_PROTOCOLS[creds.v3_auth_protocol],
                privProtocol=_PRIV_PROTOCOLS[creds.v3_priv_protocol],
            )
        mp_model = 0 if creds.version == SnmpVersion.V1 else 1
        return CommunityData(creds.community or "public", mpModel=mp_model)

    async def _target(self, host: str, creds: SnmpCredentials) -> UdpTransportTarget:
        return await UdpTransportTarget.create(
            (host, creds.port), timeout=self.timeout, retries=self.retries
        )

    async def get(self, host: str, creds: SnmpCredentials, *oids: str) -> dict[str, Any]:
        error_ind, error_status, _error_index, var_binds = await get_cmd(
            self.engine,
            self._auth(creds),
            await self._target(host, creds),
            ContextData(),
            *(ObjectType(ObjectIdentity(oid)) for oid in oids),
            lookupMib=False,
        )
        if error_ind:
            raise SnmpError(str(error_ind))
        if error_status:
            # noSuchName (v1) for one OID fails the whole PDU; retry OIDs individually.
            if len(oids) > 1:
                merged: dict[str, Any] = {}
                for oid in oids:
                    try:
                        merged.update(await self.get(host, creds, oid))
                    except SnmpError:
                        merged[oid] = None
                return merged
            raise SnmpError(error_status.prettyPrint())
        return {str(name): _convert(val) for name, val in var_binds}

    async def walk(self, host: str, creds: SnmpCredentials, oid: str) -> dict[str, Any]:
        """Walk a subtree; returns ``{index_suffix: value}``."""
        prefix = oid + "."
        out: dict[str, Any] = {}
        target = await self._target(host, creds)
        if creds.version == SnmpVersion.V1:
            iterator = walk_cmd(
                self.engine, self._auth(creds), target, ContextData(),
                ObjectType(ObjectIdentity(oid)), lexicographicMode=False, lookupMib=False,
            )  # fmt: skip
        else:
            iterator = bulk_walk_cmd(
                self.engine, self._auth(creds), target, ContextData(), 0, 25,
                ObjectType(ObjectIdentity(oid)), lexicographicMode=False, lookupMib=False,
            )  # fmt: skip
        async for error_ind, error_status, _idx, var_binds in iterator:
            if error_ind:
                raise SnmpError(str(error_ind))
            if error_status:
                break  # end of subtree / unsupported - return what we have
            for name, val in var_binds:
                name_s = str(name)
                if not name_s.startswith(prefix):
                    return out
                converted = _convert(val)
                if converted is not None:
                    out[name_s[len(prefix) :]] = converted
            if len(out) > MAX_INTERFACES * 4:
                break
        return out

    async def _safe_walk(self, host: str, creds: SnmpCredentials, oid: str) -> dict[str, Any]:
        try:
            return await self.walk(host, creds, oid)
        except SnmpError:
            return {}

    # ------------------------------------------------------------------ high level
    async def system_info(self, host: str, creds: SnmpCredentials) -> dict[str, Any]:
        values = await self.get(host, creds, SYS_DESCR, SYS_OBJECT_ID, SYS_UPTIME, SYS_NAME)
        uptime = values.get(SYS_UPTIME)
        return {
            "sys_descr": values.get(SYS_DESCR),
            "sys_object_id": values.get(SYS_OBJECT_ID),
            "uptime_seconds": int(uptime) // 100 if isinstance(uptime, int) else None,
            "sys_name": values.get(SYS_NAME),
        }

    async def poll(self, host: str, creds: SnmpCredentials) -> SnmpSnapshot:
        snap = SnmpSnapshot()
        info = await self.system_info(host, creds)  # raises if the agent is unreachable
        snap.sys_descr = info["sys_descr"]
        snap.sys_object_id = info["sys_object_id"]
        snap.uptime_seconds = info["uptime_seconds"]
        snap.sys_name = info["sys_name"]
        snap.requests += 1

        snap.cpu_percent, n = await self._cpu(host, creds)
        snap.requests += n
        snap.memory_percent, n = await self._memory(host, creds)
        snap.requests += n
        snap.interfaces, n = await self._interfaces(host, creds)
        snap.requests += n
        return snap

    async def _cpu(self, host: str, creds: SnmpCredentials) -> tuple[float | None, int]:
        loads = [v for v in (await self._safe_walk(host, creds, HR_PROCESSOR_LOAD)).values()
                 if isinstance(v, int)]  # fmt: skip
        if loads:
            return round(sum(loads) / len(loads), 2), 1
        try:
            idle = (await self.get(host, creds, UCD_CPU_IDLE)).get(UCD_CPU_IDLE)
        except SnmpError:
            return None, 2
        return (round(100.0 - idle, 2) if isinstance(idle, int) else None), 2

    async def _memory(self, host: str, creds: SnmpCredentials) -> tuple[float | None, int]:
        try:
            vals = await self.get(
                host, creds, UCD_MEM_TOTAL, UCD_MEM_AVAIL, UCD_MEM_BUFFER, UCD_MEM_CACHED
            )
        except SnmpError:
            vals = {}
        total, avail = vals.get(UCD_MEM_TOTAL), vals.get(UCD_MEM_AVAIL)
        if isinstance(total, int) and isinstance(avail, int) and total > 0:
            reclaimable = sum(v for k in (UCD_MEM_BUFFER, UCD_MEM_CACHED)
                              if isinstance(v := vals.get(k), int))  # fmt: skip
            used = max(0, total - avail - reclaimable)
            return round(100.0 * used / total, 2), 1

        types = await self._safe_walk(host, creds, HR_STORAGE_TYPE)
        ram_idx = [idx for idx, t in types.items() if str(t) == HR_STORAGE_RAM]
        if not ram_idx:
            return None, 2
        size_table = await self._safe_walk(host, creds, HR_STORAGE_SIZE)
        used_table = await self._safe_walk(host, creds, HR_STORAGE_USED)
        size, used_units = size_table.get(ram_idx[0]), used_table.get(ram_idx[0])
        if isinstance(size, int) and size > 0 and isinstance(used_units, int):
            return round(100.0 * used_units / size, 2), 4
        return None, 4

    async def _interfaces(
        self, host: str, creds: SnmpCredentials
    ) -> tuple[list[InterfaceCounters], int]:
        descr = await self._safe_walk(host, creds, IF_DESCR)
        if not descr:
            return [], 1
        tables = {
            oid: await self._safe_walk(host, creds, oid)
            for oid in (IF_TYPE, IF_SPEED, IF_ADMIN_STATUS, IF_OPER_STATUS, IF_NAME, IF_ALIAS,
                        IF_HIGH_SPEED, IF_HC_IN_OCTETS, IF_HC_OUT_OCTETS)
        }  # fmt: skip
        has_hc = bool(tables[IF_HC_IN_OCTETS])
        if not has_hc:
            tables[IF_IN_OCTETS] = await self._safe_walk(host, creds, IF_IN_OCTETS)
            tables[IF_OUT_OCTETS] = await self._safe_walk(host, creds, IF_OUT_OCTETS)
        requests = 1 + len(tables)

        result: list[InterfaceCounters] = []
        for idx, name in list(descr.items())[:MAX_INTERFACES]:
            try:
                if_index = int(idx)
            except ValueError:
                continue
            high_speed = tables[IF_HIGH_SPEED].get(idx)
            speed = tables[IF_SPEED].get(idx)
            if isinstance(high_speed, int) and high_speed > 0:
                speed_mbps: float | None = float(high_speed)
            elif isinstance(speed, int) and speed > 0:
                speed_mbps = speed / 1_000_000
            else:
                speed_mbps = None
            in_oid, out_oid = (IF_HC_IN_OCTETS, IF_HC_OUT_OCTETS) if has_hc else (
                IF_IN_OCTETS, IF_OUT_OCTETS)  # fmt: skip
            result.append(
                InterfaceCounters(
                    if_index=if_index,
                    name=str(tables[IF_NAME].get(idx) or name),
                    alias=tables[IF_ALIAS].get(idx) or None,
                    if_type=tables[IF_TYPE].get(idx),
                    admin_status=_IF_STATUS.get(tables[IF_ADMIN_STATUS].get(idx, 4), "unknown"),
                    oper_status=_IF_STATUS.get(tables[IF_OPER_STATUS].get(idx, 4), "unknown"),
                    speed_mbps=speed_mbps,
                    in_octets=tables[in_oid].get(idx),
                    out_octets=tables[out_oid].get(idx),
                    counters_64bit=has_hc,
                )
            )
        return result, requests
