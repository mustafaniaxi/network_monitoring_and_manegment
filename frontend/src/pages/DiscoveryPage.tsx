import { Import, Radar } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router";

import { useImportHosts, useScans, useStartScan } from "@/api/hooks";
import type { DeviceType, DiscoveredHost, ScanJob } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, EmptyState, PageHeader } from "@/components/ui/Card";
import { Field, Input, Select, Toggle } from "@/components/ui/Form";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/lib/cn";
import { DEVICE_TYPE_LABEL, formatDateTime, formatMs } from "@/lib/format";

interface Draft {
  selected: boolean;
  name: string;
  device_type: DeviceType;
}

function defaultName(h: DiscoveredHost): string {
  return (
    h.sys_name ||
    h.hostname?.split(".")[0] ||
    `${DEVICE_TYPE_LABEL[h.suggested_type]} ${h.ip_address}`
  );
}

function ScanResults({ job }: { job: ScanJob }) {
  const { canEdit } = useAuth();
  const { notify } = useToast();
  const importHosts = useImportHosts();
  // Only the user's edits are state; defaults are derived from the scan results.
  const [edits, setEdits] = useState<Record<string, Partial<Draft>>>({});
  const [snmp, setSnmp] = useState(false);
  const [community, setCommunity] = useState("public");

  const drafts: Record<string, Draft> = Object.fromEntries(
    job.hosts.map((h) => [
      h.ip_address,
      {
        selected: h.existing_device_id === null,
        name: defaultName(h),
        device_type: h.suggested_type,
        ...edits[h.ip_address],
      },
    ]),
  );

  const selectable = job.hosts.filter((h) => h.existing_device_id === null);
  const selected = selectable.filter((h) => drafts[h.ip_address]?.selected);
  const update = (ip: string, patch: Partial<Draft>) =>
    setEdits((e) => ({ ...e, [ip]: { ...e[ip], ...patch } }));

  async function runImport() {
    try {
      const result = await importHosts.mutateAsync({
        hosts: selected.map((h) => ({
          ip_address: h.ip_address,
          name: drafts[h.ip_address].name,
          device_type: drafts[h.ip_address].device_type,
        })),
        snmp_enabled: snmp,
        snmp_community: snmp ? community : undefined,
      });
      notify(
        "success",
        `${result.created.length} devices added`,
        result.skipped.length
          ? `${result.skipped.length} skipped (already registered)`
          : "Monitoring starts immediately.",
      );
    } catch (err) {
      notify("error", "Import failed", err instanceof Error ? err.message : undefined);
    }
  }

  const running = job.status === "running" || job.status === "pending";
  const progress = job.total ? Math.round((job.scanned / job.total) * 100) : 0;

  return (
    <Card
      title={`Scan of ${job.cidr}`}
      description={`${job.method.toUpperCase()} sweep · started ${formatDateTime(job.created_at)} by ${job.created_by}`}
      bodyClassName="p-0"
      actions={
        <Badge className={job.status === "failed" ? "text-critical-text" : undefined}>
          {job.status}
        </Badge>
      }
    >
      <div className="border-b border-line px-4 py-3">
        <div className="mb-1.5 flex justify-between text-xs text-ink-2">
          <span>
            {job.scanned} / {job.total} addresses probed
          </span>
          <span>{job.found} responding</span>
        </div>
        <div
          className="h-1.5 rounded-full bg-surface-2"
          role="progressbar"
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Scan progress"
        >
          <div
            className={cn(
              "h-1.5 rounded-full bg-accent transition-all",
              running && "animate-pulse",
            )}
            style={{ width: `${progress}%` }}
          />
        </div>
        {job.error && <p className="mt-2 text-xs text-critical-text">{job.error}</p>}
      </div>
      {job.hosts.length === 0 ? (
        <EmptyState
          title={running ? "Scanning…" : "No hosts responded"}
          description={
            running
              ? "Responding hosts appear here as they are found."
              : "Check the range, or try TCP discovery for hosts that block ping."
          }
        />
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-line bg-surface-2 text-left text-xs text-ink-2">
                <tr>
                  <th className="w-10 px-4 py-2">
                    <span className="sr-only">Select</span>
                  </th>
                  <th className="px-4 py-2 font-medium">Address</th>
                  <th className="px-4 py-2 font-medium">Name</th>
                  <th className="px-4 py-2 font-medium">Type</th>
                  <th className="px-4 py-2 text-right font-medium">RTT</th>
                  <th className="px-4 py-2 font-medium">Fingerprint</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {job.hosts.map((h) => {
                  const draft = drafts[h.ip_address];
                  const known = h.existing_device_id !== null;
                  return (
                    <tr key={h.ip_address} className={cn(known && "opacity-60")}>
                      <td className="px-4 py-2">
                        <input
                          type="checkbox"
                          className="size-4 accent-[var(--accent)]"
                          aria-label={`Select ${h.ip_address}`}
                          disabled={known || !canEdit}
                          checked={!!draft?.selected && !known}
                          onChange={(e) => update(h.ip_address, { selected: e.target.checked })}
                        />
                      </td>
                      <td className="px-4 py-2 font-mono text-xs">{h.ip_address}</td>
                      <td className="px-4 py-2">
                        {known ? (
                          <Link
                            to={`/devices/${h.existing_device_id}`}
                            className="text-xs text-accent hover:underline"
                          >
                            Already monitored
                          </Link>
                        ) : (
                          <Input
                            aria-label={`Name for ${h.ip_address}`}
                            className="h-8 min-w-44"
                            value={draft?.name ?? ""}
                            onChange={(e) => update(h.ip_address, { name: e.target.value })}
                          />
                        )}
                      </td>
                      <td className="px-4 py-2">
                        <Select
                          aria-label={`Type for ${h.ip_address}`}
                          className="h-8 min-w-36"
                          disabled={known}
                          value={draft?.device_type ?? h.suggested_type}
                          onChange={(e) =>
                            update(h.ip_address, { device_type: e.target.value as DeviceType })
                          }
                        >
                          {Object.entries(DEVICE_TYPE_LABEL).map(([v, l]) => (
                            <option key={v} value={v}>
                              {l}
                            </option>
                          ))}
                        </Select>
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {formatMs(h.latency_ms)}
                      </td>
                      <td className="max-w-xs px-4 py-2 text-xs text-ink-muted">
                        <p className="truncate" title={h.sys_descr ?? undefined}>
                          {h.sys_descr ?? h.hostname ?? "—"}
                        </p>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {canEdit && selectable.length > 0 && (
            <div className="flex flex-wrap items-end justify-between gap-4 border-t border-line px-4 py-3">
              <div className="flex flex-wrap items-end gap-4">
                <Toggle
                  checked={snmp}
                  onChange={setSnmp}
                  label="Enable SNMP"
                  description="Collect CPU, memory and interfaces"
                />
                {snmp && (
                  <Field label="Community">
                    {(id) => (
                      <Input
                        id={id}
                        type="password"
                        className="h-8 w-40"
                        value={community}
                        onChange={(e) => setCommunity(e.target.value)}
                      />
                    )}
                  </Field>
                )}
              </div>
              <Button
                variant="primary"
                icon={<Import className="size-4" />}
                disabled={selected.length === 0}
                loading={importHosts.isPending}
                onClick={runImport}
              >
                Add {selected.length} device{selected.length === 1 ? "" : "s"}
              </Button>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

export function DiscoveryPage() {
  const { canEdit } = useAuth();
  const { notify } = useToast();
  const scans = useScans();
  const start = useStartScan();
  const [cidr, setCidr] = useState("192.168.1.0/24");
  const [method, setMethod] = useState<"icmp" | "tcp">("icmp");
  const [port, setPort] = useState("22");
  const [community, setCommunity] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const jobs = useMemo(() => scans.data ?? [], [scans.data]);
  const current = jobs.find((j) => j.id === selectedId) ?? jobs[0];

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      const job = await start.mutateAsync({
        cidr: cidr.trim(),
        method,
        tcp_port: method === "tcp" ? Number(port) : undefined,
        snmp_community: community.trim() || undefined,
      });
      setSelectedId(job.id);
    } catch (err) {
      notify("error", "Could not start scan", err instanceof Error ? err.message : undefined);
    }
  }

  return (
    <>
      <PageHeader
        title="Network discovery"
        description="Sweep a subnet for responding hosts, fingerprint them over SNMP and add them in bulk."
      />
      <div className="grid gap-4 xl:grid-cols-[20rem_1fr]">
        <div className="flex flex-col gap-4">
          <Card title="New scan">
            <form onSubmit={submit} className="space-y-4">
              <Field label="Network (CIDR)" hint="e.g. 192.168.1.0/24 - up to 1024 addresses">
                {(id) => (
                  <Input
                    id={id}
                    required
                    value={cidr}
                    onChange={(e) => setCidr(e.target.value)}
                    disabled={!canEdit}
                  />
                )}
              </Field>
              <Field label="Probe">
                {(id) => (
                  <Select
                    id={id}
                    value={method}
                    onChange={(e) => setMethod(e.target.value as "icmp" | "tcp")}
                    disabled={!canEdit}
                  >
                    <option value="icmp">ICMP ping</option>
                    <option value="tcp">TCP connect</option>
                  </Select>
                )}
              </Field>
              {method === "tcp" && (
                <Field label="TCP port">
                  {(id) => (
                    <Input
                      id={id}
                      type="number"
                      min={1}
                      max={65535}
                      value={port}
                      onChange={(e) => setPort(e.target.value)}
                    />
                  )}
                </Field>
              )}
              <Field
                label="SNMP community (optional)"
                hint="Used to fingerprint vendor and device type"
              >
                {(id) => (
                  <Input
                    id={id}
                    type="password"
                    autoComplete="off"
                    value={community}
                    onChange={(e) => setCommunity(e.target.value)}
                    disabled={!canEdit}
                  />
                )}
              </Field>
              <Button
                type="submit"
                variant="primary"
                className="w-full"
                icon={<Radar className="size-4" />}
                loading={start.isPending}
                disabled={!canEdit}
              >
                Start scan
              </Button>
              {!canEdit && (
                <p className="text-xs text-ink-muted">
                  Operators and administrators can run scans.
                </p>
              )}
            </form>
          </Card>
          {jobs.length > 0 && (
            <Card title="Recent scans" bodyClassName="p-0">
              <ul className="divide-y divide-line">
                {jobs.map((j) => (
                  <li key={j.id}>
                    <button
                      onClick={() => setSelectedId(j.id)}
                      className={cn(
                        "flex w-full items-center justify-between px-4 py-2.5 text-left text-sm hover:bg-surface-hover",
                        current?.id === j.id && "bg-accent-soft",
                      )}
                    >
                      <span>
                        <span className="block font-mono text-xs">{j.cidr}</span>
                        <span className="text-xs text-ink-muted">
                          {formatDateTime(j.created_at)}
                        </span>
                      </span>
                      <span className="text-xs text-ink-2">
                        {j.status === "running" ? `${j.scanned}/${j.total}` : `${j.found} found`}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
        {current ? (
          <ScanResults key={current.id} job={current} />
        ) : (
          <div className="card">
            <EmptyState
              icon={<Radar className="size-8" />}
              title="No scans yet"
              description="Start a scan to find devices on your network. Responding hosts can be added to monitoring in one click."
            />
          </div>
        )}
      </div>
    </>
  );
}
