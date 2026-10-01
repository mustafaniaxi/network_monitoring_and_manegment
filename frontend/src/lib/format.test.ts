import { describe, expect, it } from "vitest";

import {
  formatBps,
  formatBpsShort,
  formatBytes,
  formatDuration,
  formatMs,
  formatPercent,
  formatRelative,
} from "./format";

describe("formatBps", () => {
  it("scales units and keeps ~3 significant figures", () => {
    expect(formatBps(950)).toBe("950 bit/s");
    expect(formatBps(9_860_000)).toBe("9.9 Mbit/s");
    expect(formatBps(98_500_000)).toBe("98.5 Mbit/s");
    expect(formatBps(967_700_000)).toBe("968 Mbit/s");
    expect(formatBps(1_200_000_000)).toBe("1.2 Gbit/s");
  });
  it("honours explicit digits and missing values", () => {
    expect(formatBps(1_000_000_000, 0)).toBe("1 Gbit/s");
    expect(formatBps(null)).toBe("—");
    expect(formatBps(Number.NaN)).toBe("—");
  });
  it("produces compact axis labels", () => {
    expect(formatBpsShort(1_500_000_000)).toBe("1.5G");
    expect(formatBpsShort(350_000_000)).toBe("350M");
    expect(formatBpsShort(0)).toBe("0");
  });
});

describe("other formatters", () => {
  it("formats latency by magnitude", () => {
    expect(formatMs(0.456)).toBe("0.46 ms");
    expect(formatMs(12.34)).toBe("12.3 ms");
    expect(formatMs(250.4)).toBe("250 ms");
    expect(formatMs(undefined)).toBe("—");
  });
  it("formats percentages, bytes and durations", () => {
    expect(formatPercent(99.456, 2)).toBe("99.46%");
    expect(formatBytes(1536)).toBe("1.5 KiB");
    expect(formatDuration(42)).toBe("42s");
    expect(formatDuration(3 * 60 + 5)).toBe("3m 5s");
    expect(formatDuration(2 * 3600 + 15 * 60)).toBe("2h 15m");
    expect(formatDuration(3 * 86400 + 4 * 3600)).toBe("3d 4h");
  });
  it("formats relative times", () => {
    const now = Date.parse("2026-01-01T12:00:00Z");
    expect(formatRelative(null, now)).toBe("never");
    expect(formatRelative("2026-01-01T11:59:58Z", now)).toBe("just now");
    expect(formatRelative("2026-01-01T11:58:00Z", now)).toBe("2m ago");
    expect(formatRelative("2025-12-30T12:00:00Z", now)).toBe("2d ago");
  });
});
