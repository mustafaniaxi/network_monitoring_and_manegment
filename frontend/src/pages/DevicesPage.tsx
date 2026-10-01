import { Pencil, Plus, RefreshCw, Search, Server, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { useCheckDevice, useDeleteDevice, useDevices } from "@/api/hooks";
import type { Device, DeviceStatus, DeviceType } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { DeviceFormModal } from "@/components/DeviceFormModal";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui/Card";
import { DeviceIcon } from "@/components/ui/DeviceIcon";
import { Input, Select } from "@/components/ui/Form";
import { ConfirmDialog } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { Spinner } from "@/components/ui/Spinner";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/lib/cn";
import { DEVICE_TYPE_LABEL, formatMs, formatPercent, formatRelative } from "@/lib/format";

const PAGE_SIZE = 25;

function useDebounced<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

export function DevicesPage() {
  const { canEdit } = useAuth();
  const { notify } = useToast();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("q") ?? "");
  const status = (params.get("status") ?? "") as DeviceStatus | "";
  const deviceType = (params.get("type") ?? "") as DeviceType | "";
  const page = Number(params.get("page") ?? 1);
  const debounced = useDebounced(search);
  const [editing, setEditing] = useState<Device | "new" | null>(null);
  const [deleting, setDeleting] = useState<Device | null>(null);

  const query = useDevices({
    search: debounced,
    status,
    device_type: deviceType,
    page,
    page_size: PAGE_SIZE,
  });
  const check = useCheckDevice();
  const remove = useDeleteDevice();

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  };

  useEffect(() => {
    if (debounced !== (params.get("q") ?? "")) update("q", debounced);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  async function runCheck(device: Device) {
    try {
      const result = await check.mutateAsync(device.id);
      notify(
        result.status === "down" ? "warning" : "success",
        `${result.name}: ${result.status === "down" ? "no response" : formatMs(result.last_latency_ms)}`,
      );
    } catch (err) {
      notify("error", "Check failed", err instanceof Error ? err.message : undefined);
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    try {
      await remove.mutateAsync(deleting.id);
      notify("success", `${deleting.name} deleted`);
      setDeleting(null);
    } catch (err) {
      notify("error", "Delete failed", err instanceof Error ? err.message : undefined);
    }
  }

  const data = query.data;
  return (
    <>
      <PageHeader
        title="Devices"
        description="Inventory of monitored network devices."
        actions={
          canEdit && (
            <Button
              variant="primary"
              icon={<Plus className="size-4" />}
              onClick={() => setEditing("new")}
            >
              Add device
            </Button>
          )
        }
      />

      <div className="mb-4 flex flex-wrap gap-2">
        <div className="relative w-full sm:w-72">
          <Search
            className="pointer-events-none absolute top-2.5 left-3 size-4 text-ink-muted"
            aria-hidden
          />
          <Input
            aria-label="Search devices"
            placeholder="Search name, IP, location, vendor"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select
          aria-label="Filter by status"
          value={status}
          onChange={(e) => update("status", e.target.value)}
          className="w-40"
        >
          <option value="">All statuses</option>
          <option value="up">Online</option>
          <option value="degraded">Degraded</option>
          <option value="down">Offline</option>
          <option value="unknown">Unknown</option>
        </Select>
        <Select
          aria-label="Filter by type"
          value={deviceType}
          onChange={(e) => update("type", e.target.value)}
          className="w-44"
        >
          <option value="">All types</option>
          {Object.entries(DEVICE_TYPE_LABEL).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </Select>
      </div>

      {query.isError && <ErrorState error={query.error} onRetry={() => query.refetch()} />}
      <div
        className={cn(
          "card overflow-hidden transition-opacity",
          query.isPlaceholderData && "opacity-60",
        )}
      >
        {!data ? (
          <div className="p-6">
            <Spinner />
          </div>
        ) : data.items.length === 0 ? (
          <EmptyState
            icon={<Server className="size-8" />}
            title="No devices found"
            description={
              debounced || status || deviceType
                ? "Try different filters."
                : "Add a device or discover your network."
            }
            action={
              canEdit &&
              !debounced && (
                <Link to="/discovery" className="text-sm font-medium text-accent hover:underline">
                  Run a discovery scan
                </Link>
              )
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-line bg-surface-2 text-left text-xs text-ink-2">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Device</th>
                  <th className="px-4 py-2.5 font-medium">IP address</th>
                  <th className="px-4 py-2.5 font-medium">Type</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5 text-right font-medium">Latency</th>
                  <th className="px-4 py-2.5 text-right font-medium">Loss</th>
                  <th className="px-4 py-2.5 text-right font-medium">CPU</th>
                  <th className="px-4 py-2.5 font-medium">Last check</th>
                  {canEdit && (
                    <th className="px-4 py-2.5">
                      <span className="sr-only">Actions</span>
                    </th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.items.map((d) => (
                  <tr key={d.id} className="hover:bg-surface-hover/60">
                    <td className="px-4 py-2.5">
                      <Link
                        to={`/devices/${d.id}`}
                        className="flex items-center gap-2.5 font-medium hover:text-accent"
                      >
                        <DeviceIcon type={d.device_type} className="size-4 text-ink-muted" />
                        <span className="truncate">{d.name}</span>
                      </Link>
                      {d.location && <p className="pl-6.5 text-xs text-ink-muted">{d.location}</p>}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs">{d.ip_address}</td>
                    <td className="px-4 py-2.5 text-ink-2">{DEVICE_TYPE_LABEL[d.device_type]}</td>
                    <td className="px-4 py-2.5">
                      <StatusBadge status={d.status} monitored={d.is_monitored} />
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      {formatMs(d.last_latency_ms)}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      {formatPercent(d.last_packet_loss, 0)}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      {formatPercent(d.last_cpu_percent, 0)}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-ink-muted">
                      {formatRelative(d.last_checked_at)}
                    </td>
                    {canEdit && (
                      <td className="px-4 py-2.5">
                        <div className="flex justify-end gap-0.5">
                          <Button
                            size="sm"
                            variant="ghost"
                            aria-label={`Check ${d.name} now`}
                            title="Check now"
                            loading={check.isPending && check.variables === d.id}
                            icon={<RefreshCw className="size-3.5" />}
                            onClick={() => runCheck(d)}
                          />
                          <Button
                            size="sm"
                            variant="ghost"
                            aria-label={`Edit ${d.name}`}
                            title="Edit"
                            icon={<Pencil className="size-3.5" />}
                            onClick={() => setEditing(d)}
                          />
                          <Button
                            size="sm"
                            variant="ghost"
                            aria-label={`Delete ${d.name}`}
                            title="Delete"
                            icon={<Trash2 className="size-3.5" />}
                            onClick={() => setDeleting(d)}
                          />
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && data.total > 0 && (
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={data.total}
            onPage={(p) => update("page", String(p))}
          />
        )}
      </div>

      {editing && (
        <DeviceFormModal
          open
          device={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)}
        />
      )}
      <ConfirmDialog
        open={!!deleting}
        title="Delete device"
        message={
          <>
            Delete <strong>{deleting?.name}</strong> and all of its measurements, interfaces, links
            and alerts? This cannot be undone.
          </>
        }
        loading={remove.isPending}
        onConfirm={confirmDelete}
        onClose={() => setDeleting(null)}
      />
    </>
  );
}
