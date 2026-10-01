import { ArrowLeft, Download, Pencil, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { download } from "@/api/client";
import {
  useCheckDevice,
  useDevice,
  useDeviceAlerts,
  useDeviceInterfaces,
  useDeviceMetrics,
} from "@/api/hooks";
import type { TimeRange } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { ChartCard } from "@/components/charts/ChartCard";
import { RangePicker } from "@/components/charts/RangePicker";
import { TimeSeriesChart, type Series } from "@/components/charts/TimeSeriesChart";
import { DeviceFormModal } from "@/components/DeviceFormModal";
import { AlertStatusBadge, SeverityBadge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, EmptyState, ErrorState } from "@/components/ui/Card";
import { DeviceIcon } from "@/components/ui/DeviceIcon";
import { Spinner } from "@/components/ui/Spinner";
import { StatTile } from "@/components/ui/StatTile";
import { useToast } from "@/components/ui/Toast";
import {
  DEVICE_TYPE_LABEL,
  RANGE_SECONDS,
  formatBps,
  formatBpsShort,
  formatDateTime,
  formatDuration,
  formatMs,
  formatPercent,
  formatRelative,
} from "@/lib/format";

const LATENCY: Series[] = [
  { key: "latency_ms", label: "Average", color: "var(--series-1)" },
  { key: "latency_max_ms", label: "Maximum", color: "var(--series-2)" },
];
const AVAILABILITY: Series[] = [
  { key: "availability", label: "Availability", color: "var(--series-1)" },
];
const LOSS: Series[] = [{ key: "packet_loss", label: "Packet loss", color: "var(--series-1)" }];
const RESOURCES: Series[] = [
  { key: "cpu_percent", label: "CPU", color: "var(--series-1)" },
  { key: "memory_percent", label: "Memory", color: "var(--series-2)" },
];
const TRAFFIC: Series[] = [
  { key: "in_bps", label: "Inbound", color: "var(--series-1)" },
  { key: "out_bps", label: "Outbound", color: "var(--series-2)" },
];

function Info({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className="mt-0.5 truncate text-sm">{value || "—"}</dd>
    </div>
  );
}

export function DeviceDetailPage() {
  const id = Number(useParams().id);
  const { canEdit } = useAuth();
  const { notify } = useToast();
  const [range, setRange] = useState<TimeRange>("6h");
  const [editing, setEditing] = useState(false);
  const device = useDevice(id);
  const metrics = useDeviceMetrics(id, range);
  const interfaces = useDeviceInterfaces(id);
  const alerts = useDeviceAlerts(id);
  const check = useCheckDevice();

  if (device.isError) return <ErrorState error={device.error} onRetry={() => device.refetch()} />;
  if (!device.data) return <Spinner label="Loading device" />;
  const d = device.data;
  const points = metrics.data?.points ?? [];
  const rangeSeconds = RANGE_SECONDS[range];
  const fetching = metrics.isPlaceholderData;
  const pct = (v: number) => formatPercent(v);

  return (
    <>
      <Link
        to="/devices"
        className="mb-3 inline-flex items-center gap-1 text-xs text-ink-2 hover:text-ink"
      >
        <ArrowLeft className="size-3.5" /> Devices
      </Link>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="grid size-11 place-items-center rounded-xl bg-accent-soft text-accent">
            <DeviceIcon type={d.device_type} className="size-5" />
          </div>
          <div>
            <h1 className="flex flex-wrap items-center gap-2 text-xl font-semibold tracking-tight">
              {d.name} <StatusBadge status={d.status} monitored={d.is_monitored} />
            </h1>
            <p className="text-sm text-ink-2">
              <span className="font-mono">{d.ip_address}</span> · {DEVICE_TYPE_LABEL[d.device_type]}
              {d.location && ` · ${d.location}`}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <RangePicker value={range} onChange={setRange} />
          <Button
            size="md"
            icon={<Download className="size-4" />}
            onClick={() =>
              download("/reports/samples.csv", { range, device_id: id }, `${d.name}-${range}.csv`)
            }
          >
            Export
          </Button>
          {canEdit && (
            <>
              <Button
                icon={<RefreshCw className="size-4" />}
                loading={check.isPending}
                onClick={() =>
                  check.mutateAsync(id).then(
                    (r) =>
                      notify(
                        r.status === "down" ? "warning" : "success",
                        r.status === "down"
                          ? "No response"
                          : `Reachable in ${formatMs(r.last_latency_ms)}`,
                      ),
                    (err: Error) => notify("error", "Check failed", err.message),
                  )
                }
              >
                Check now
              </Button>
              <Button icon={<Pencil className="size-4" />} onClick={() => setEditing(true)}>
                Edit
              </Button>
            </>
          )}
        </div>
      </div>

      {d.last_error && (
        <div className="mb-4 rounded-lg border border-warning/50 bg-warning/5 px-4 py-2.5 text-sm text-warning-text">
          Last poll: {d.last_error}
        </div>
      )}

      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatTile
          label="Latency"
          value={d.status === "down" ? "—" : formatMs(d.last_latency_ms)}
          sub={`checked ${formatRelative(d.last_checked_at)}`}
        />
        <StatTile
          label="Packet loss"
          value={formatPercent(d.last_packet_loss, 0)}
          tone={
            (d.last_packet_loss ?? 0) >= 100
              ? "critical"
              : (d.last_packet_loss ?? 0) > 0
                ? "warning"
                : undefined
          }
        />
        <StatTile
          label="CPU"
          value={formatPercent(d.last_cpu_percent)}
          sub={d.snmp_enabled ? "via SNMP" : "SNMP disabled"}
          tone={(d.last_cpu_percent ?? 0) > 90 ? "critical" : undefined}
        />
        <StatTile
          label="Memory"
          value={formatPercent(d.last_memory_percent)}
          sub={d.snmp_enabled ? "via SNMP" : "SNMP disabled"}
        />
        <StatTile
          label="Traffic in / out"
          value={<span className="text-lg">{formatBps(d.last_in_bps)}</span>}
          sub={formatBps(d.last_out_bps) + " out"}
        />
        <StatTile
          label="Uptime"
          value={formatDuration(d.uptime_seconds)}
          sub={`last seen ${formatRelative(d.last_seen_at)}`}
        />
      </div>

      <div className="mb-5 grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Latency"
          description="Round-trip time per bucket"
          data={points}
          series={LATENCY}
          format={formatMs}
          fetching={fetching}
        >
          <TimeSeriesChart
            data={points}
            series={LATENCY}
            format={formatMs}
            axisFormat={(v) => `${v} ms`}
            rangeSeconds={rangeSeconds}
          />
        </ChartCard>
        <ChartCard
          title="Availability"
          description="Share of successful probes"
          data={points}
          series={AVAILABILITY}
          format={pct}
          fetching={fetching}
        >
          <TimeSeriesChart
            data={points}
            series={AVAILABILITY}
            format={pct}
            axisFormat={(v) => `${v}%`}
            domain={[0, 100]}
            rangeSeconds={rangeSeconds}
          />
        </ChartCard>
        <ChartCard title="Packet loss" data={points} series={LOSS} format={pct} fetching={fetching}>
          <TimeSeriesChart
            data={points}
            series={LOSS}
            format={pct}
            axisFormat={(v) => `${v}%`}
            domain={[0, "auto"]}
            rangeSeconds={rangeSeconds}
          />
        </ChartCard>
        {d.snmp_enabled && (
          <>
            <ChartCard
              title="CPU and memory"
              description="Utilisation reported by SNMP"
              data={points}
              series={RESOURCES}
              format={pct}
              fetching={fetching}
            >
              <TimeSeriesChart
                data={points}
                series={RESOURCES}
                format={pct}
                axisFormat={(v) => `${v}%`}
                domain={[0, 100]}
                rangeSeconds={rangeSeconds}
              />
            </ChartCard>
            <ChartCard
              title="Traffic"
              description="All active interfaces"
              data={points}
              series={TRAFFIC}
              format={(v) => formatBps(v)}
              fetching={fetching}
              className="lg:col-span-2"
            >
              <TimeSeriesChart
                variant="area"
                data={points}
                series={TRAFFIC}
                format={(v) => formatBps(v)}
                axisFormat={formatBpsShort}
                rangeSeconds={rangeSeconds}
              />
            </ChartCard>
          </>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card
          title="Interfaces"
          description="IF-MIB, refreshed every poll"
          className="lg:col-span-2"
          bodyClassName="p-0"
        >
          {!d.snmp_enabled || (interfaces.data?.length ?? 0) === 0 ? (
            <EmptyState
              title={d.snmp_enabled ? "No interface data yet" : "SNMP is disabled"}
              description={
                d.snmp_enabled
                  ? "Interfaces appear after the first successful SNMP poll."
                  : "Enable SNMP to collect interface status and bandwidth."
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-line bg-surface-2 text-left text-xs text-ink-2">
                  <tr>
                    <th className="px-4 py-2 font-medium">Interface</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                    <th className="px-4 py-2 text-right font-medium">Speed</th>
                    <th className="px-4 py-2 text-right font-medium">In</th>
                    <th className="px-4 py-2 text-right font-medium">Out</th>
                    <th className="px-4 py-2 text-right font-medium">Utilisation</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {interfaces.data?.map((i) => (
                    <tr key={i.id}>
                      <td className="px-4 py-2">
                        <p className="font-medium">{i.name}</p>
                        {i.alias && <p className="text-xs text-ink-muted">{i.alias}</p>}
                      </td>
                      <td className="px-4 py-2">
                        <StatusBadge
                          status={
                            i.oper_status === "up"
                              ? "up"
                              : i.admin_status === "down"
                                ? "unknown"
                                : "down"
                          }
                        />
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {i.speed_mbps ? formatBps(i.speed_mbps * 1e6, 0) : "—"}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">{formatBps(i.in_bps)}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{formatBps(i.out_bps)}</td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {formatPercent(i.utilization_percent)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <div className="flex flex-col gap-4">
          <Card title="Details">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
              <Info label="Vendor" value={d.vendor} />
              <Info label="Model" value={d.model} />
              <Info label="SNMP name" value={d.sys_name} />
              <Info
                label="Check method"
                value={d.check_method === "tcp" ? `TCP/${d.tcp_port}` : "ICMP ping"}
              />
              <Info
                label="Poll interval"
                value={d.poll_interval_seconds ? `${d.poll_interval_seconds}s` : "default"}
              />
              <Info label="Status since" value={formatDateTime(d.status_changed_at)} />
              <div className="col-span-2">
                <Info
                  label="System description"
                  value={
                    <span className="whitespace-normal text-xs text-ink-2">{d.sys_descr}</span>
                  }
                />
              </div>
              {d.tags.length > 0 && (
                <div className="col-span-2 flex flex-wrap gap-1">
                  {d.tags.map((t) => (
                    <span key={t} className="rounded bg-surface-2 px-1.5 py-0.5 text-xs text-ink-2">
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </dl>
          </Card>
          <Card title="Recent alerts" bodyClassName="p-0">
            {(alerts.data?.length ?? 0) === 0 ? (
              <EmptyState title="No alerts for this device" />
            ) : (
              <ul className="max-h-80 divide-y divide-line overflow-y-auto">
                {alerts.data?.map((a) => (
                  <li key={a.id} className="px-4 py-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex gap-1.5">
                        <SeverityBadge severity={a.severity} />
                        <AlertStatusBadge status={a.status} />
                      </div>
                      <span className="text-xs text-ink-muted">
                        {formatRelative(a.triggered_at)}
                      </span>
                    </div>
                    <p className="mt-1 text-sm">{a.message}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      {editing && <DeviceFormModal open device={d} onClose={() => setEditing(false)} />}
    </>
  );
}
