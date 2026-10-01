from __future__ import annotations

import asyncio

import pytest

from netmon.services.monitoring.probes import TcpProber, summarise_rtts
from netmon.services.monitoring.rates import (
    COUNTER32_MAX,
    COUNTER64_MAX,
    counter_delta,
    octets_to_bps,
    utilization,
)


def test_counter_delta_without_wrap():
    assert counter_delta(100, 250, is_64bit=False) == 150


def test_counter_delta_handles_32bit_wrap():
    assert counter_delta(COUNTER32_MAX - 10, 5, is_64bit=False) == 15


def test_counter_delta_handles_64bit_wrap():
    assert counter_delta(COUNTER64_MAX - 1, 1, is_64bit=True) == 2


def test_octets_to_bps():
    assert octets_to_bps(0, 1_250_000, 1.0, False) == 10_000_000


@pytest.mark.parametrize(
    ("prev", "cur", "elapsed"), [(None, 10, 1.0), (10, None, 1.0), (1, 2, 0.0), (1, 2, -1.0)]
)
def test_octets_to_bps_missing_data(prev, cur, elapsed):
    assert octets_to_bps(prev, cur, elapsed, False) is None


def test_implausible_rate_after_counter_reset_is_discarded():
    # A reboot resets the counter; the "wrap" would imply ~34 Gbit/s on a 100 Mbit/s port.
    assert octets_to_bps(4_000_000_000, 1000, 1.0, False, speed_mbps=100) is None


def test_utilization_uses_busiest_direction():
    assert utilization(10_000_000, 50_000_000, 100) == 50.0
    assert utilization(500_000_000, None, 100) == 100.0  # capped
    assert utilization(None, None, 100) is None
    assert utilization(1, 1, None) is None


def test_summarise_rtts():
    result = summarise_rtts([1.0, 3.0, 2.0], sent=4)
    assert result.is_up
    assert result.latency_ms == 2.0
    assert result.min_ms == 1.0 and result.max_ms == 3.0
    assert result.jitter_ms == 1.5
    assert result.packet_loss == 25.0
    assert not summarise_rtts([], sent=3).is_up


async def test_tcp_prober_against_local_server():
    server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        result = await TcpProber(timeout=1.0, attempts=2).probe("127.0.0.1", port)
    assert result.is_up and result.packet_loss == 0 and result.packets_sent == 2


async def test_tcp_prober_closed_port():
    server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()
    result = await TcpProber(timeout=0.5, attempts=1).probe("127.0.0.1", port)
    assert not result.is_up and result.error
