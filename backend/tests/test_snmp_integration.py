"""Integration test of the SNMP collector against a real net-snmp agent.

Skipped automatically when ``snmpd`` is not installed (``apt install snmpd``); CI installs it.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from netmon.models import SnmpAuthProtocol, SnmpPrivProtocol, SnmpVersion
from netmon.services.monitoring.snmp import SnmpClient, SnmpError
from netmon.services.monitoring.types import SnmpCredentials

pytestmark = [
    pytest.mark.snmp,
    pytest.mark.skipif(shutil.which("snmpd") is None, reason="snmpd not installed"),
]


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def agent_port(tmp_path_factory: pytest.TempPathFactory) -> Iterator[int]:
    workdir: Path = tmp_path_factory.mktemp("snmpd")
    port = _free_udp_port()
    conf = workdir / "snmpd.conf"
    conf.write_text(
        f"agentaddress udp:127.0.0.1:{port}\n"
        "rocommunity netmon-test 127.0.0.1\n"
        'createUser labv3 SHA "auth-pass-123" AES "priv-pass-123"\n'
        "rouser labv3 priv\n"
        "sysName netmon-test-agent\n"
    )
    command = [shutil.which("snmpd") or "snmpd", "-f", "-C", "-c", str(conf),
               "-Lf", str(workdir / "snmpd.log"), f"--persistentDir={workdir}"]  # fmt: skip
    proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
    time.sleep(1.0)
    if proc.poll() is not None:
        pytest.skip("snmpd failed to start in this environment")
    yield port
    proc.terminate()
    proc.wait(timeout=5)


@pytest.mark.parametrize("version", [SnmpVersion.V1, SnmpVersion.V2C])
async def test_poll_with_community(agent_port: int, version: SnmpVersion) -> None:
    client = SnmpClient(timeout=2, retries=1)
    try:
        snap = await client.poll(
            "127.0.0.1", SnmpCredentials(version=version, port=agent_port, community="netmon-test")
        )
    finally:
        client.close()
    assert snap.sys_name == "netmon-test-agent"
    assert snap.uptime_seconds is not None
    assert snap.interfaces, "IF-MIB should expose at least the loopback interface"
    loopback = next(i for i in snap.interfaces if i.is_loopback)
    assert loopback.in_octets is not None
    # Counter64 (ifHCInOctets) only exists in SNMPv2c/v3.
    assert loopback.counters_64bit is (version != SnmpVersion.V1)


async def test_poll_with_snmpv3_auth_priv(agent_port: int) -> None:
    client = SnmpClient(timeout=2, retries=1)
    creds = SnmpCredentials(
        version=SnmpVersion.V3, port=agent_port, v3_username="labv3",
        v3_auth_protocol=SnmpAuthProtocol.SHA, v3_auth_key="auth-pass-123",
        v3_priv_protocol=SnmpPrivProtocol.AES128, v3_priv_key="priv-pass-123",
    )  # fmt: skip
    try:
        info = await client.system_info("127.0.0.1", creds)
    finally:
        client.close()
    assert info["sys_name"] == "netmon-test-agent"


async def test_wrong_community_times_out(agent_port: int) -> None:
    client = SnmpClient(timeout=0.5, retries=0)
    try:
        with pytest.raises(SnmpError):
            await client.poll("127.0.0.1", SnmpCredentials(port=agent_port, community="wrong"))
    finally:
        client.close()
