import { Download, TrendingDown } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { download } from "@/api/client";
import {
  useAvailabilityReport,
  useBottlenecks,
  useDegradation,
  useDetectionReport,
  useTopFailing,
  useTrafficHeatmap,
} from "@/api/hooks";
import type { AvailabilityRow, TimeRange } from "@/api/types";
import { BarList } from "@/components/charts/BarList";
import { TrafficHeatmapGrid } from "@/components/charts/Heatmap";
import { RangePicker } from "@/components/charts/RangePicker";
import { Badge, StatusDot } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, EmptyState, PageHeader } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { StatTile } from "@/components/ui/StatTile";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/lib/cn";
import { formatBps, formatDuration, formatMs, formatPercent } from "@/lib/format";

type SortKey = "name" | "availability" | "avg_latency_ms" | "incidents" | "downtime_seconds";

function AvailabilityTable({ rows }: { rows: AvailabilityRow[] }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "availability", dir: 1 });
  const sorted = [...rows].sort((a, b) => {
    const av = a[sort.key] ?? (sort.key === "availability" ? 101 : -1);
    const bv = b[sort.key] ?? (sort.key === "availability" ? 101 : -1);
    return (av < bv ? -1 : av > bv ? 1 : 0) * sort.dir;
  });
  const header = (key: SortKey, label: string, right = false) => (
    <th
      className={cn("px-4 py-2.5 font-medium", right && "text-right")}
      aria-sort={sort.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
    >
      <button
        className="hover:text-ink"
        onClick={() => setSort((s) => ({ key, dir: s.key === key ? (-s.dir as 1 | -1) : 1 }))}
      >
        {label}
        {sort.key === key && (sort.dir === 1 ? " ↑" : " ↓")}
      </button>
    </th>
  );
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="border-b border-line bg-surface-2 text-left text-xs text-ink-2">
          <tr>
            {header("name", "Device")}
            {header("availability", "Availability", true)}
            {header("avg_latency_ms", "Avg latency", true)}
            <th className="px-4 py-2.5 text-right font-medium">Max latency</th>
            <th className="px-4 py-2.5 text-right font-medium">Jitter</th>
            <th className="px-4 py-2.5 text-right font-medium">Loss</th>
            {header("incidents", "Outages", true)}
            {header("downtime_seconds", "Downtime", true)}
            <th className="px-4 py-2.5 text-right font-medium">MTTR</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {sorted.map((r) => (
            <tr key={r.device_id}>
              <td className="px-4 py-2">
                <Link
                  to={`/devices/${r.device_id}`}
                  className="flex items-center gap-2 font-medium hover:text-accent"
                >
                  <StatusDot status={r.status} /> {r.name}
                </Link>
              </td>
              <td
                className={cn(
                  "px-4 py-2 text-right font-medium tabular-nums",
                  r.availability !== null && r.availability < 99 && "text-critical-text",
                  r.availability !== null &&
                    r.availability >= 99 &&
                    r.availability < 99.9 &&
                    "text-warning-text",
                )}
              >
                {formatPercent(r.availability, 3)}
              </td>
              <td className="px-4 py-2 text-right tabular-nums">{formatMs(r.avg_latency_ms)}</td>
              <td className="px-4 py-2 text-right tabular-nums">{formatMs(r.max_latency_ms)}</td>
              <td className="px-4 py-2 text-right tabular-nums">{formatMs(r.avg_jitter_ms)}</td>
              <td className="px-4 py-2 text-right tabular-nums">
                {formatPercent(r.avg_packet_loss, 2)}
              </td>
              <td className="px-4 py-2 text-right tabular-nums">{r.incidents}</td>
              <td className="px-4 py-2 text-right tabular-nums">
                {r.downtime_seconds ? formatDuration(r.downtime_seconds) : "—"}
              </td>
              <td className="px-4 py-2 text-right tabular-nums">
                {formatDuration(r.mttr_seconds)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ReportsPage() {
  const [range, setRange] = useState<TimeRange>("7d");
  const { notify } = useToast();
  const availability = useAvailabilityReport(range);
  const failing = useTopFailing(range);
  const heatmap = useTrafficHeatmap(range);
  const bottlenecks = useBottlenecks(range);
  const degradation = useDegradation(range);
  const detection = useDetectionReport(range);

  const exportCsv = (path: string, name: string) =>
    download(path, { range }, `${name}-${range}.csv`).catch((err: Error) =>
      notify("error", "Export failed", err.message),
    );

  const rows = availability.data ?? [];
  const measured = rows.filter((r) => r.availability !== null);
  const overall = measured.length
    ? measured.reduce((s, r) => s + (r.availability ?? 0) * r.samples, 0) /
      Math.max(
        1,
        measured.reduce((s, r) => s + r.samples, 0),
      )
    : null;
  const totalDowntime = rows.reduce((s, r) => s + r.downtime_seconds, 0);
  const degraded = (degradation.data ?? []).filter((d) => d.degraded);
  const peak = heatmap.data?.peak;
  const days = heatmap.data?.days ?? [];

  return (
    <>
      <PageHeader
        title="Reports & analytics"
        description="Historical analysis: availability, failures, traffic patterns, bottlenecks and degradation."
        actions={
          <>
            <RangePicker value={range} onChange={setRange} />
            <Button
              icon={<Download className="size-4" />}
              onClick={() => exportCsv("/reports/availability.csv", "availability")}
            >
              Availability CSV
            </Button>
            <Button
              icon={<Download className="size-4" />}
              onClick={() => exportCsv("/reports/samples.csv", "samples")}
            >
              Raw samples CSV
            </Button>
          </>
        }
      />

      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatTile
          label="Network availability"
          value={formatPercent(overall, 3)}
          sub="Sample-weighted"
        />
        <StatTile
          label="Outages"
          value={detection.data?.outages ?? "—"}
          sub="Device-unreachable alerts"
        />
        <StatTile label="Total downtime" value={formatDuration(totalDowntime)} sub="All devices" />
        <StatTile
          label="Mean time to detect"
          value={formatDuration(detection.data?.detection_delay_seconds.mean)}
          sub="First failed probe → alert"
        />
        <StatTile
          label="Mean time to recover"
          value={formatDuration(detection.data?.time_to_recovery_seconds.mean)}
          sub={`median ${formatDuration(detection.data?.time_to_recovery_seconds.median)}`}
        />
        <StatTile
          label="Degrading devices"
          value={degraded.length}
          tone={degraded.length ? "warning" : undefined}
          sub="2nd half vs 1st half"
        />
      </div>

      <Card
        title="Availability by device"
        description="Uptime, latency and outage statistics for the selected period"
        className="mb-5"
        bodyClassName={cn("p-0 transition-opacity", availability.isPlaceholderData && "opacity-60")}
      >
        {!availability.data ? (
          <div className="p-6">
            <Spinner />
          </div>
        ) : rows.length === 0 ? (
          <EmptyState title="No devices" />
        ) : (
          <AvailabilityTable rows={rows} />
        )}
      </Card>

      <div className="mb-5 grid gap-4 lg:grid-cols-3">
        <Card title="Most frequently failing" description="Outages in the period">
          {(failing.data?.length ?? 0) === 0 ? (
            <EmptyState title="No outages recorded" />
          ) : (
            <BarList
              items={(failing.data ?? []).map((r) => ({
                key: String(r.device_id),
                label: r.name,
                value: r.incidents,
              }))}
              format={(v) => `${v} outage${v === 1 ? "" : "s"}`}
            />
          )}
        </Card>
        <Card
          title="High-traffic periods"
          description={
            peak
              ? `Busiest: ${days[peak.day]} ${String(peak.hour).padStart(2, "0")}:00 at ${formatBps(peak.bps)}`
              : "Average total throughput by weekday and hour (local time)"
          }
          className="lg:col-span-2"
        >
          {heatmap.data ? (
            <TrafficHeatmapGrid days={days} matrix={heatmap.data.matrix_bps} />
          ) : (
            <Spinner />
          )}
        </Card>
      </div>

      <div className="mb-5 grid gap-4 lg:grid-cols-2">
        <Card
          title="Potential bottlenecks"
          description="Devices ranked by link utilisation, CPU and loss"
          bodyClassName="p-0"
        >
          {(bottlenecks.data?.devices.length ?? 0) === 0 ? (
            <EmptyState
              title="No utilisation data"
              description="Bottleneck analysis needs SNMP-enabled devices."
            />
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-line bg-surface-2 text-left text-xs text-ink-2">
                <tr>
                  <th className="px-4 py-2 font-medium">Device</th>
                  <th className="px-4 py-2 text-right font-medium">Avg / max link</th>
                  <th className="px-4 py-2 text-right font-medium">Avg / max CPU</th>
                  <th className="px-4 py-2 text-right font-medium">Loss</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {bottlenecks.data?.devices.slice(0, 8).map((d) => (
                  <tr key={d.device_id}>
                    <td className="px-4 py-2">
                      <Link to={`/devices/${d.device_id}`} className="hover:text-accent">
                        {d.name}
                      </Link>
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {formatPercent(d.avg_bandwidth_util, 0)} /{" "}
                      {formatPercent(d.max_bandwidth_util, 0)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {formatPercent(d.avg_cpu_percent, 0)} / {formatPercent(d.max_cpu_percent, 0)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {formatPercent(d.avg_packet_loss, 2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <Card
          title="Busiest interfaces"
          description="Current utilisation of the most loaded ports"
          bodyClassName="p-0"
        >
          {(bottlenecks.data?.interfaces.length ?? 0) === 0 ? (
            <EmptyState title="No interface data" />
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-line bg-surface-2 text-left text-xs text-ink-2">
                <tr>
                  <th className="px-4 py-2 font-medium">Interface</th>
                  <th className="px-4 py-2 text-right font-medium">Speed</th>
                  <th className="px-4 py-2 text-right font-medium">In / out</th>
                  <th className="px-4 py-2 text-right font-medium">Utilisation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {bottlenecks.data?.interfaces.map((i) => (
                  <tr key={`${i.device_id}-${i.interface}`}>
                    <td className="px-4 py-2">
                      <p className="font-medium">{i.interface}</p>
                      <p className="text-xs text-ink-muted">{i.device}</p>
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {i.speed_mbps ? formatBps(i.speed_mbps * 1e6, 0) : "—"}
                    </td>
                    <td className="px-4 py-2 text-right text-xs tabular-nums">
                      {formatBps(i.in_bps)} / {formatBps(i.out_bps)}
                    </td>
                    <td
                      className={cn(
                        "px-4 py-2 text-right font-medium tabular-nums",
                        (i.utilization_percent ?? 0) >= 80 && "text-critical-text",
                      )}
                    >
                      {formatPercent(i.utilization_percent)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <Card
        title="Performance degradation"
        description="Average latency, loss and availability: first half of the period vs second half"
        bodyClassName="p-0"
      >
        {(degradation.data?.length ?? 0) === 0 ? (
          <EmptyState
            icon={<TrendingDown className="size-8" />}
            title="Not enough history"
            description="Needs measurements in both halves of the selected period."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-line bg-surface-2 text-left text-xs text-ink-2">
                <tr>
                  <th className="px-4 py-2 font-medium">Device</th>
                  <th className="px-4 py-2 text-right font-medium">Latency before → after</th>
                  <th className="px-4 py-2 text-right font-medium">Change</th>
                  <th className="px-4 py-2 text-right font-medium">Loss before → after</th>
                  <th className="px-4 py-2 text-right font-medium">Availability before → after</th>
                  <th className="px-4 py-2 font-medium">Assessment</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {degradation.data?.map((r) => (
                  <tr key={r.device_id}>
                    <td className="px-4 py-2">
                      <Link to={`/devices/${r.device_id}`} className="hover:text-accent">
                        {r.name}
                      </Link>
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {formatMs(r.latency_before_ms)} → {formatMs(r.latency_after_ms)}
                    </td>
                    <td
                      className={cn(
                        "px-4 py-2 text-right tabular-nums",
                        (r.latency_change_percent ?? 0) > 50 && "text-critical-text",
                      )}
                    >
                      {r.latency_change_percent === null
                        ? "—"
                        : `${r.latency_change_percent > 0 ? "+" : ""}${r.latency_change_percent}%`}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {formatPercent(r.packet_loss_before, 2)} →{" "}
                      {formatPercent(r.packet_loss_after, 2)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {formatPercent(r.availability_before, 2)} →{" "}
                      {formatPercent(r.availability_after, 2)}
                    </td>
                    <td className="px-4 py-2">
                      {r.degraded ? (
                        <Badge className="border-warning/50 text-warning-text">Degrading</Badge>
                      ) : (
                        <Badge>Stable</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
