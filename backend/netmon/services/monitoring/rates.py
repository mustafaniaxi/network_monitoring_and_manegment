"""Traffic-rate math for SNMP interface counters."""

from __future__ import annotations

COUNTER32_MAX = 2**32
COUNTER64_MAX = 2**64


def counter_delta(previous: int, current: int, is_64bit: bool) -> int:
    """Difference between two samples of a monotonically increasing counter, handling wrap."""
    if current >= previous:
        return current - previous
    return current + (COUNTER64_MAX if is_64bit else COUNTER32_MAX) - previous


def octets_to_bps(
    previous: int | None,
    current: int | None,
    elapsed_seconds: float,
    is_64bit: bool,
    speed_mbps: float | None = None,
) -> float | None:
    """Convert two octet counter readings into bits per second.

    Returns ``None`` when a rate cannot be computed reliably: missing readings, non-positive
    interval, or an implausible result (above 2x link speed), which typically means the
    counter was reset by a reboot rather than wrapped.
    """
    if previous is None or current is None or elapsed_seconds <= 0:
        return None
    bps = counter_delta(previous, current, is_64bit) * 8 / elapsed_seconds
    if speed_mbps and bps > speed_mbps * 1_000_000 * 2:
        return None
    return bps


def utilization(
    in_bps: float | None, out_bps: float | None, speed_mbps: float | None
) -> float | None:
    """Percentage utilisation of the busier direction (links are full-duplex)."""
    if not speed_mbps or (in_bps is None and out_bps is None):
        return None
    busiest = max(in_bps or 0.0, out_bps or 0.0)
    return round(min(100.0, 100.0 * busiest / (speed_mbps * 1_000_000)), 2)
