/** Formatting helpers for network quantities. All return "—" for missing values. */

export const DASH = "—";

const isNum = (v: number | null | undefined): v is number =>
  typeof v === "number" && Number.isFinite(v);

export function formatBps(bps: number | null | undefined, digits?: number): string {
  if (!isNum(bps)) return DASH;
  const units = ["bit/s", "kbit/s", "Mbit/s", "Gbit/s", "Tbit/s"];
  let value = bps;
  let unit = 0;
  while (Math.abs(value) >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit += 1;
  }
  // About three significant figures by default: 9.9 Mbit/s, 98.5 Mbit/s, 985 Mbit/s.
  const decimals = digits ?? (unit === 0 || Math.abs(value) >= 100 ? 0 : 1);
  return `${value.toFixed(decimals)} ${units[unit]}`;
}

/** Compact axis label: 12M, 1.5G. */
export function formatBpsShort(bps: number): string {
  const abs = Math.abs(bps);
  if (abs >= 1e9) return `${+(bps / 1e9).toFixed(1)}G`;
  if (abs >= 1e6) return `${+(bps / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${+(bps / 1e3).toFixed(1)}k`;
  return `${Math.round(bps)}`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!isNum(bytes)) return DASH;
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function formatMs(ms: number | null | undefined): string {
  if (!isNum(ms)) return DASH;
  if (ms < 1) return `${ms.toFixed(2)} ms`;
  if (ms < 100) return `${ms.toFixed(1)} ms`;
  return `${Math.round(ms)} ms`;
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (!isNum(value)) return DASH;
  return `${value.toFixed(digits)}%`;
}

export function formatNumber(value: number | null | undefined): string {
  if (!isNum(value)) return DASH;
  return new Intl.NumberFormat().format(value);
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!isNum(seconds)) return DASH;
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m ${s % 60}s`;
}

export function formatRelative(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "never";
  const diff = (now - new Date(iso).getTime()) / 1000;
  if (diff < 5) return "just now";
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Axis tick label adapted to the span of the selected range. */
export function formatTick(iso: string, rangeSeconds: number): string {
  const d = new Date(iso);
  if (rangeSeconds <= 86400) {
    return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export const RANGE_SECONDS = {
  "1h": 3600,
  "6h": 6 * 3600,
  "24h": 86400,
  "7d": 7 * 86400,
  "30d": 30 * 86400,
} as const;

export const DEVICE_TYPE_LABEL: Record<string, string> = {
  router: "Router",
  switch: "Switch",
  firewall: "Firewall",
  server: "Server",
  pc: "PC",
  access_point: "Access point",
  printer: "Printer",
  cloud: "Internet / cloud",
  other: "Other",
};

export const METRIC_LABEL: Record<string, string> = {
  device_down: "Device unreachable",
  latency_ms: "Latency (ms)",
  packet_loss: "Packet loss (%)",
  cpu_percent: "CPU (%)",
  memory_percent: "Memory (%)",
  bandwidth_util: "Bandwidth utilisation (%)",
};

export const OPERATOR_SYMBOL: Record<string, string> = { gt: ">", gte: "≥", lt: "<", lte: "≤" };
