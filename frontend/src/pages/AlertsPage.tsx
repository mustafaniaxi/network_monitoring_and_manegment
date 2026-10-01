import { Bell, Check, CheckCheck, Pencil, Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import {
  useAlertAction,
  useAlertRules,
  useAlerts,
  useAlertSummary,
  useAllDevices,
  useDeleteRule,
  useSaveRule,
} from "@/api/hooks";
import type {
  AlertMetric,
  AlertOperator,
  AlertRule,
  AlertSeverity,
  AlertStatus,
  DeviceType,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { AlertStatusBadge, SeverityBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui/Card";
import { Field, Input, Segmented, Select, Toggle } from "@/components/ui/Form";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { Spinner } from "@/components/ui/Spinner";
import { StatTile } from "@/components/ui/StatTile";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/lib/cn";
import {
  DEVICE_TYPE_LABEL,
  METRIC_LABEL,
  OPERATOR_SYMBOL,
  formatDateTime,
  formatDuration,
} from "@/lib/format";

type View = "open" | "resolved" | "all";
const STATUS_FILTER: Record<View, AlertStatus[] | undefined> = {
  open: ["active", "acknowledged"],
  resolved: ["resolved"],
  all: undefined,
};

function AlertList() {
  const { canEdit } = useAuth();
  const { notify } = useToast();
  const [view, setView] = useState<View>("open");
  const [severity, setSeverity] = useState<AlertSeverity | "">("");
  const [page, setPage] = useState(1);
  const query = useAlerts({
    status: STATUS_FILTER[view],
    severity: severity ? [severity] : undefined,
    page,
    page_size: 25,
  });
  const action = useAlertAction();

  async function act(id: number, kind: "acknowledge" | "resolve") {
    try {
      await action.mutateAsync({ id, action: kind });
      notify("success", kind === "acknowledge" ? "Alert acknowledged" : "Alert resolved");
    } catch (err) {
      notify("error", "Action failed", err instanceof Error ? err.message : undefined);
    }
  }

  // Open alerts' durations are measured up to the moment the data was fetched.
  const now = query.dataUpdatedAt;
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Segmented
          label="Alert state"
          value={view}
          onChange={(v) => {
            setView(v);
            setPage(1);
          }}
          options={[
            { value: "open", label: "Open" },
            { value: "resolved", label: "Resolved" },
            { value: "all", label: "All" },
          ]}
        />
        <Select
          aria-label="Severity"
          className="w-40"
          value={severity}
          onChange={(e) => {
            setSeverity(e.target.value as AlertSeverity | "");
            setPage(1);
          }}
        >
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </Select>
      </div>
      {query.isError && <ErrorState error={query.error} onRetry={() => query.refetch()} />}
      <div className={cn("card overflow-hidden", query.isPlaceholderData && "opacity-60")}>
        {!query.data ? (
          <div className="p-6">
            <Spinner />
          </div>
        ) : query.data.items.length === 0 ? (
          <EmptyState
            icon={<Bell className="size-8" />}
            title={view === "open" ? "No open alerts" : "No alerts"}
            description="Alerts appear here when a rule is breached."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-line bg-surface-2 text-left text-xs text-ink-2">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Severity</th>
                  <th className="px-4 py-2.5 font-medium">Alert</th>
                  <th className="px-4 py-2.5 font-medium">Device</th>
                  <th className="px-4 py-2.5 font-medium">Triggered</th>
                  <th className="px-4 py-2.5 font-medium">Duration</th>
                  <th className="px-4 py-2.5 font-medium">State</th>
                  {canEdit && (
                    <th className="px-4 py-2.5">
                      <span className="sr-only">Actions</span>
                    </th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {query.data.items.map((a) => {
                  const end = a.resolved_at ? new Date(a.resolved_at).getTime() : now;
                  const start = new Date(a.first_breach_at ?? a.triggered_at).getTime();
                  return (
                    <tr key={a.id}>
                      <td className="px-4 py-2.5">
                        <SeverityBadge severity={a.severity} />
                      </td>
                      <td className="max-w-md px-4 py-2.5">
                        <p className="font-medium">{a.title}</p>
                        <p className="text-xs text-ink-2">{a.message}</p>
                        {a.resolution_note && a.status !== "active" && (
                          <p className="mt-0.5 text-xs text-ink-muted">{a.resolution_note}</p>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        <Link to={`/devices/${a.device_id}`} className="hover:text-accent">
                          {a.device_name ?? `#${a.device_id}`}
                        </Link>
                      </td>
                      <td className="px-4 py-2.5 text-xs text-ink-2">
                        {formatDateTime(a.triggered_at)}
                      </td>
                      <td className="px-4 py-2.5 text-xs tabular-nums">
                        {formatDuration((end - start) / 1000)}
                      </td>
                      <td className="px-4 py-2.5">
                        <AlertStatusBadge status={a.status} />
                      </td>
                      {canEdit && (
                        <td className="px-4 py-2.5">
                          <div className="flex justify-end gap-1">
                            {a.status === "active" && (
                              <Button
                                size="sm"
                                icon={<Check className="size-3.5" />}
                                onClick={() => act(a.id, "acknowledge")}
                              >
                                Ack
                              </Button>
                            )}
                            {a.status !== "resolved" && (
                              <Button
                                size="sm"
                                icon={<CheckCheck className="size-3.5" />}
                                onClick={() => act(a.id, "resolve")}
                              >
                                Resolve
                              </Button>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {query.data && query.data.total > 0 && (
          <Pagination page={page} pageSize={25} total={query.data.total} onPage={setPage} />
        )}
      </div>
    </>
  );
}

const METRICS: AlertMetric[] = [
  "device_down",
  "latency_ms",
  "packet_loss",
  "cpu_percent",
  "memory_percent",
  "bandwidth_util",
];

function RuleModal({ rule, onClose }: { rule?: AlertRule; onClose: () => void }) {
  const save = useSaveRule();
  const devices = useAllDevices();
  const { notify } = useToast();
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: rule?.name ?? "",
    description: rule?.description ?? "",
    metric: rule?.metric ?? ("latency_ms" as AlertMetric),
    operator: rule?.operator ?? ("gt" as AlertOperator),
    threshold: String(rule?.threshold ?? 100),
    consecutive: String(rule?.consecutive ?? 2),
    severity: rule?.severity ?? ("warning" as AlertSeverity),
    scope: rule?.device_id ? "device" : rule?.device_type ? "type" : "all",
    device_type: rule?.device_type ?? ("router" as DeviceType),
    device_id: String(rule?.device_id ?? ""),
    enabled: rule?.enabled ?? true,
  });
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) =>
    setForm((f) => ({ ...f, [k]: v }));
  const isDown = form.metric === "device_down";

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const common = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      operator: form.operator,
      threshold: Number(form.threshold),
      consecutive: Number(form.consecutive),
      severity: form.severity,
      enabled: form.enabled,
    };
    try {
      if (rule) {
        await save.mutateAsync({ id: rule.id, payload: common });
      } else {
        await save.mutateAsync({
          payload: {
            ...common,
            metric: form.metric,
            device_type: form.scope === "type" ? form.device_type : null,
            device_id: form.scope === "device" ? Number(form.device_id) : null,
          },
        });
      }
      notify("success", rule ? "Rule updated" : "Rule created");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save rule");
    }
  }

  return (
    <Modal
      open
      title={rule ? `Edit rule: ${rule.name}` : "New alert rule"}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" form="rule-form" variant="primary" loading={save.isPending}>
            Save rule
          </Button>
        </>
      }
    >
      <form id="rule-form" onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <Field label="Name" className="sm:col-span-2">
          {(id) => (
            <Input
              id={id}
              required
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
            />
          )}
        </Field>
        <Field
          label="Metric"
          hint={rule ? "Metric and scope cannot change; create a new rule instead." : undefined}
        >
          {(id) => (
            <Select
              id={id}
              disabled={!!rule}
              value={form.metric}
              onChange={(e) => set("metric", e.target.value as AlertMetric)}
            >
              {METRICS.map((m) => (
                <option key={m} value={m}>
                  {METRIC_LABEL[m]}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Severity">
          {(id) => (
            <Select
              id={id}
              value={form.severity}
              onChange={(e) => set("severity", e.target.value as AlertSeverity)}
            >
              <option value="critical">Critical</option>
              <option value="warning">Warning</option>
              <option value="info">Info</option>
            </Select>
          )}
        </Field>
        {!isDown && (
          <>
            <Field label="Condition">
              {(id) => (
                <Select
                  id={id}
                  value={form.operator}
                  onChange={(e) => set("operator", e.target.value as AlertOperator)}
                >
                  {(["gt", "gte", "lt", "lte"] as const).map((o) => (
                    <option key={o} value={o}>
                      {OPERATOR_SYMBOL[o]}{" "}
                      {o === "gt"
                        ? "greater than"
                        : o === "gte"
                          ? "at least"
                          : o === "lt"
                            ? "less than"
                            : "at most"}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Threshold">
              {(id) => (
                <Input
                  id={id}
                  type="number"
                  step="any"
                  required
                  value={form.threshold}
                  onChange={(e) => set("threshold", e.target.value)}
                />
              )}
            </Field>
          </>
        )}
        <Field
          label="Consecutive breaches"
          hint="Samples in a row before the alert fires (debouncing)."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              min={1}
              max={100}
              required
              value={form.consecutive}
              onChange={(e) => set("consecutive", e.target.value)}
            />
          )}
        </Field>
        <Field label="Applies to">
          {(id) => (
            <Select
              id={id}
              disabled={!!rule}
              value={form.scope}
              onChange={(e) => set("scope", e.target.value)}
            >
              <option value="all">All devices</option>
              <option value="type">A device type</option>
              <option value="device">One device</option>
            </Select>
          )}
        </Field>
        {form.scope === "type" && (
          <Field label="Device type">
            {(id) => (
              <Select
                id={id}
                disabled={!!rule}
                value={form.device_type}
                onChange={(e) => set("device_type", e.target.value as DeviceType)}
              >
                {Object.entries(DEVICE_TYPE_LABEL).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        )}
        {form.scope === "device" && (
          <Field label="Device">
            {(id) => (
              <Select
                id={id}
                disabled={!!rule}
                required
                value={form.device_id}
                onChange={(e) => set("device_id", e.target.value)}
              >
                <option value="">Select…</option>
                {devices.data?.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        )}
        <Field label="Description" className="sm:col-span-2">
          {(id) => (
            <Input
              id={id}
              value={form.description}
              onChange={(e) => set("description", e.target.value)}
            />
          )}
        </Field>
        <div className="sm:col-span-2">
          <Toggle checked={form.enabled} onChange={(v) => set("enabled", v)} label="Enabled" />
        </div>
        <p className="text-xs text-ink-muted sm:col-span-2">
          More specific rules win: a device rule overrides a type rule, which overrides a global
          rule for the same metric.
        </p>
        {error && (
          <p role="alert" className="text-sm text-critical-text sm:col-span-2">
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}

function RuleList() {
  const { canEdit } = useAuth();
  const rules = useAlertRules();
  const devices = useAllDevices();
  const save = useSaveRule();
  const remove = useDeleteRule();
  const { notify } = useToast();
  const [editing, setEditing] = useState<AlertRule | "new" | null>(null);
  const [deleting, setDeleting] = useState<AlertRule | null>(null);
  const deviceName = (id: number) => devices.data?.find((d) => d.id === id)?.name ?? `#${id}`;

  if (rules.isError) return <ErrorState error={rules.error} onRetry={() => rules.refetch()} />;
  return (
    <>
      {canEdit && (
        <div className="mb-4 flex justify-end">
          <Button
            variant="primary"
            icon={<Plus className="size-4" />}
            onClick={() => setEditing("new")}
          >
            New rule
          </Button>
        </div>
      )}
      <div className="card overflow-hidden">
        {!rules.data ? (
          <div className="p-6">
            <Spinner />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-line bg-surface-2 text-left text-xs text-ink-2">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Rule</th>
                  <th className="px-4 py-2.5 font-medium">Condition</th>
                  <th className="px-4 py-2.5 font-medium">Scope</th>
                  <th className="px-4 py-2.5 font-medium">Severity</th>
                  <th className="px-4 py-2.5 font-medium">Enabled</th>
                  {canEdit && (
                    <th className="px-4 py-2.5">
                      <span className="sr-only">Actions</span>
                    </th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rules.data.map((r) => (
                  <tr key={r.id} className={cn(!r.enabled && "opacity-60")}>
                    <td className="px-4 py-2.5">
                      <p className="font-medium">{r.name}</p>
                      {r.description && <p className="text-xs text-ink-muted">{r.description}</p>}
                    </td>
                    <td className="px-4 py-2.5 text-xs">
                      {r.metric === "device_down"
                        ? "No response"
                        : `${METRIC_LABEL[r.metric]} ${OPERATOR_SYMBOL[r.operator]} ${r.threshold}`}
                      <span className="text-ink-muted"> · {r.consecutive}× in a row</span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-ink-2">
                      {r.device_id
                        ? deviceName(r.device_id)
                        : r.device_type
                          ? `All ${DEVICE_TYPE_LABEL[r.device_type].toLowerCase()}s`
                          : "All devices"}
                    </td>
                    <td className="px-4 py-2.5">
                      <SeverityBadge severity={r.severity} />
                    </td>
                    <td className="px-4 py-2.5">
                      <input
                        type="checkbox"
                        aria-label={`${r.enabled ? "Disable" : "Enable"} ${r.name}`}
                        className="size-4 accent-[var(--accent)]"
                        checked={r.enabled}
                        disabled={!canEdit}
                        onChange={(e) =>
                          save.mutate({ id: r.id, payload: { enabled: e.target.checked } })
                        }
                      />
                    </td>
                    {canEdit && (
                      <td className="px-4 py-2.5">
                        <div className="flex justify-end gap-0.5">
                          <Button
                            size="sm"
                            variant="ghost"
                            aria-label={`Edit ${r.name}`}
                            icon={<Pencil className="size-3.5" />}
                            onClick={() => setEditing(r)}
                          />
                          <Button
                            size="sm"
                            variant="ghost"
                            aria-label={`Delete ${r.name}`}
                            icon={<Trash2 className="size-3.5" />}
                            onClick={() => setDeleting(r)}
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
      </div>
      {editing && (
        <RuleModal
          rule={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)}
        />
      )}
      <ConfirmDialog
        open={!!deleting}
        title="Delete rule"
        message={
          <>
            Delete <strong>{deleting?.name}</strong>? Its open alerts will be resolved.
          </>
        }
        loading={remove.isPending}
        onConfirm={() =>
          deleting &&
          remove.mutateAsync(deleting.id).then(
            () => {
              notify("success", "Rule deleted");
              setDeleting(null);
            },
            (err: Error) => notify("error", "Delete failed", err.message),
          )
        }
        onClose={() => setDeleting(null)}
      />
    </>
  );
}

export function AlertsPage() {
  const [tab, setTab] = useState<"alerts" | "rules">("alerts");
  const summary = useAlertSummary();
  const s = summary.data;
  return (
    <>
      <PageHeader
        title="Alerts"
        description="Threshold breaches and device outages, with automatic resolution."
        actions={
          <Segmented
            label="Section"
            value={tab}
            onChange={setTab}
            options={[
              { value: "alerts", label: "Alerts" },
              { value: "rules", label: "Rules" },
            ]}
          />
        }
      />
      {tab === "alerts" && s && (
        <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatTile label="Active" value={s.active} tone={s.active ? "critical" : undefined} />
          <StatTile label="Acknowledged" value={s.acknowledged} />
          <StatTile
            label="Critical open"
            value={s.by_severity.critical}
            tone={s.by_severity.critical ? "critical" : undefined}
          />
          <StatTile label="Resolved (24h)" value={s.resolved_24h} />
        </div>
      )}
      {tab === "alerts" ? <AlertList /> : <RuleList />}
    </>
  );
}
