import { Activity, Bell, Gauge, Server, Timer, Zap } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { useAlerts, useDashboardSummary, useDevices, useNetworkSeries } from "@/api/hooks";
import type { TimeRange } from "@/api/types";
import { BarList } from "@/components/charts/BarList";
import { ChartCard } from "@/components/charts/ChartCard";
import { RangePicker } from "@/components/charts/RangePicker";
import { TimeSeriesChart } from "@/components/charts/TimeSeriesChart";
import { SeverityBadge, StatusDot } from "@/components/ui/Badge";
import { Card, EmptyState, ErrorState, PageHeader } from "@/components/ui/Card";
import { DeviceIcon } from "@/components/ui/DeviceIcon";
import { Spinner } from "@/components/ui/Spinner";
import { StatTile } from "@/components/ui/StatTile";
import {
  DEVICE_TYPE_LABEL,
  RANGE_SECONDS,
  formatBps,
  formatBpsShort,
  formatMs,
  formatPercent,
  formatRelative,
} from "@/lib/format";

const STATUS_ORDER = { down: 0, degraded: 1, unknown: 2, up: 3 } as const;

export function DashboardPage() {
  const [range, setRange] = useState<TimeRange>("24h");
  const summary = useDashboardSummary();
  const series = useNetworkSeries(range);
  const devices = useDevices({ page_size: 500 });
  const alerts = useAlerts({ open_only: true, page_size: 6 });

  if (summary.isError)
    return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />;
  if (!summary.data) return <Spinner label="Loading dashboard" />;
  const s = summary.data;
  const points = series.data?.points ?? [];
  const rangeSeconds = RANGE_SECONDS[range];
  const attention = (devices.data?.items ?? [])
    .filter((d) => d.is_monitored)
    .sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || a.name.localeCompare(b.name))
    .slice(0, 8);
  const monitored = s.devices.total - s.devices.unmonitored;

  return (
    <>
      <PageHeader
        title="Network overview"
        description="Health and performance of every monitored device."
        actions={<RangePicker value={range} onChange={setRange} />}
      />

      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatTile
          label="Devices online"
          icon={<Server className="size-4" />}
          value={
            <>
              {s.devices.up + s.devices.degraded}
              <span className="text-base font-normal text-ink-muted"> / {monitored}</span>
            </>
          }
          sub={
            s.devices.down > 0 ? (
              <span className="text-critical-text">{s.devices.down} offline</span>
            ) : (
              "All reachable"
            )
          }
          tone={s.devices.down > 0 ? "critical" : undefined}
        />
        <StatTile
          label="Availability (24h)"
          icon={<Activity className="size-4" />}
          value={formatPercent(s.availability_24h, 2)}
          sub={`${s.samples_24h.toLocaleString()} measurements`}
        />
        <StatTile
          label="Avg latency (1h)"
          icon={<Timer className="size-4" />}
          value={formatMs(s.avg_latency_ms_1h)}
          sub="Round-trip time"
        />
        <StatTile
          label="Packet loss (1h)"
          icon={<Gauge className="size-4" />}
          value={formatPercent(s.avg_packet_loss_1h, 2)}
          tone={(s.avg_packet_loss_1h ?? 0) > 5 ? "warning" : undefined}
          sub="Average across devices"
        />
        <StatTile
          label="Throughput now"
          icon={<Zap className="size-4" />}
          value={formatBps(s.throughput_bps)}
          sub={
            s.avg_bandwidth_util !== null
              ? `Avg link utilisation ${formatPercent(s.avg_bandwidth_util)}`
              : "SNMP devices only"
          }
        />
        <StatTile
          label="Open alerts"
          icon={<Bell className="size-4" />}
          value={s.alerts.active + s.alerts.acknowledged}
          tone={s.alerts.critical > 0 ? "critical" : s.alerts.warning > 0 ? "warning" : undefined}
          sub={`${s.alerts.critical} critical · ${s.alerts.warning} warning`}
        />
      </div>

      <div className="mb-5 grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Average latency"
          description="Mean round-trip time across reachable devices"
          data={points}
          series={[{ key: "latency_ms", label: "Latency", color: "var(--series-1)" }]}
          format={formatMs}
          fetching={series.isPlaceholderData}
        >
          <TimeSeriesChart
            data={points}
            series={[{ key: "latency_ms", label: "Latency", color: "var(--series-1)" }]}
            format={formatMs}
            axisFormat={(v) => `${v} ms`}
            rangeSeconds={rangeSeconds}
          />
        </ChartCard>
        <ChartCard
          title="Network availability"
          description="Share of successful probes"
          data={points}
          series={[{ key: "availability", label: "Availability", color: "var(--series-1)" }]}
          format={(v) => formatPercent(v, 2)}
          fetching={series.isPlaceholderData}
        >
          <TimeSeriesChart
            data={points}
            series={[{ key: "availability", label: "Availability", color: "var(--series-1)" }]}
            format={(v) => formatPercent(v, 2)}
            axisFormat={(v) => `${v}%`}
            domain={[0, 100]}
            rangeSeconds={rangeSeconds}
          />
        </ChartCard>
        <ChartCard
          title="Total traffic"
          description="Sum of interface throughput reported by SNMP"
          data={points}
          series={[
            { key: "in_bps", label: "Inbound", color: "var(--series-1)" },
            { key: "out_bps", label: "Outbound", color: "var(--series-2)" },
          ]}
          format={(v) => formatBps(v)}
          fetching={series.isPlaceholderData}
        >
          <TimeSeriesChart
            variant="area"
            data={points}
            series={[
              { key: "in_bps", label: "Inbound", color: "var(--series-1)" },
              { key: "out_bps", label: "Outbound", color: "var(--series-2)" },
            ]}
            format={(v) => formatBps(v)}
            axisFormat={formatBpsShort}
            rangeSeconds={rangeSeconds}
          />
        </ChartCard>
        <ChartCard
          title="Packet loss"
          description="Average probe loss across devices"
          data={points}
          series={[{ key: "packet_loss", label: "Packet loss", color: "var(--series-1)" }]}
          format={(v) => formatPercent(v, 2)}
          fetching={series.isPlaceholderData}
        >
          <TimeSeriesChart
            data={points}
            series={[{ key: "packet_loss", label: "Packet loss", color: "var(--series-1)" }]}
            format={(v) => formatPercent(v, 2)}
            axisFormat={(v) => `${v}%`}
            rangeSeconds={rangeSeconds}
          />
        </ChartCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card
          title="Device status"
          description="Problems first"
          actions={
            <Link to="/devices" className="text-xs font-medium text-accent hover:underline">
              All devices
            </Link>
          }
          bodyClassName="p-0"
        >
          {attention.length === 0 ? (
            <EmptyState
              title="No monitored devices"
              description="Add devices or run a discovery scan."
            />
          ) : (
            <ul className="divide-y divide-line">
              {attention.map((d) => (
                <li key={d.id}>
                  <Link
                    to={`/devices/${d.id}`}
                    className="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-hover"
                  >
                    <StatusDot status={d.status} />
                    <DeviceIcon type={d.device_type} className="size-4 text-ink-muted" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{d.name}</p>
                      <p className="text-xs text-ink-muted">{d.ip_address}</p>
                    </div>
                    <div className="text-right text-xs">
                      <p className="font-medium tabular-nums">
                        {d.status === "down" ? "Offline" : formatMs(d.last_latency_ms)}
                      </p>
                      <p className="text-ink-muted">{formatRelative(d.last_checked_at)}</p>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title="Open alerts"
          actions={
            <Link to="/alerts" className="text-xs font-medium text-accent hover:underline">
              All alerts
            </Link>
          }
          bodyClassName="p-0"
        >
          {(alerts.data?.items.length ?? 0) === 0 ? (
            <EmptyState title="No open alerts" description="Everything is within thresholds." />
          ) : (
            <ul className="divide-y divide-line">
              {alerts.data?.items.map((a) => (
                <li key={a.id} className="px-4 py-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <SeverityBadge severity={a.severity} />
                    <span className="text-xs text-ink-muted">{formatRelative(a.triggered_at)}</span>
                  </div>
                  <p className="mt-1 text-sm">{a.message}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Inventory by type" description={`${s.devices.total} registered devices`}>
          <BarList
            items={Object.entries(s.by_type)
              .sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0))
              .map(([type, count]) => ({
                key: type,
                label: DEVICE_TYPE_LABEL[type] ?? type,
                value: count ?? 0,
              }))}
          />
        </Card>
      </div>
    </>
  );
}
