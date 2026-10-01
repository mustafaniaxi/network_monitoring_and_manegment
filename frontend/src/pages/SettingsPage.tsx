import { useState, type FormEvent } from "react";

import { request } from "@/api/client";
import { useChangePassword, useSystemInfo, useSystemStats } from "@/api/hooks";
import { useAuth } from "@/auth/AuthContext";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, PageHeader } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Form";
import { Spinner } from "@/components/ui/Spinner";
import { useToast } from "@/components/ui/Toast";
import {
  formatBps,
  formatBytes,
  formatDuration,
  formatNumber,
  formatPercent,
  formatRelative,
} from "@/lib/format";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1.5 text-sm">
      <dt className="text-ink-2">{label}</dt>
      <dd className="text-right font-medium tabular-nums">{value}</dd>
    </div>
  );
}

function ProfileCard() {
  const { user, refreshUser, logout } = useAuth();
  const { notify } = useToast();
  const [name, setName] = useState(user?.full_name ?? "");
  const [busy, setBusy] = useState(false);
  const change = useChangePassword();
  const [pw, setPw] = useState({ current: "", next: "", confirm: "" });
  const [pwError, setPwError] = useState<string | null>(null);

  async function saveProfile(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await request("/auth/me", { method: "PATCH", body: { full_name: name } });
      await refreshUser();
      notify("success", "Profile saved");
    } catch (err) {
      notify("error", "Could not save profile", err instanceof Error ? err.message : undefined);
    } finally {
      setBusy(false);
    }
  }

  async function changePassword(e: FormEvent) {
    e.preventDefault();
    setPwError(null);
    if (pw.next !== pw.confirm) {
      setPwError("The new passwords do not match");
      return;
    }
    try {
      await change.mutateAsync({ current_password: pw.current, new_password: pw.next });
      notify("success", "Password changed", "Please sign in with your new password.");
      logout();
    } catch (err) {
      setPwError(err instanceof Error ? err.message : "Could not change password");
    }
  }

  return (
    <Card title="Your account" description={`${user?.email} · ${user?.role}`}>
      <form onSubmit={saveProfile} className="mb-6 flex items-end gap-2">
        <Field label="Full name" className="flex-1">
          {(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Button type="submit" loading={busy}>
          Save
        </Button>
      </form>
      <form onSubmit={changePassword} className="space-y-3 border-t border-line pt-4">
        <h3 className="text-sm font-semibold">Change password</h3>
        <Field label="Current password">
          {(id) => (
            <Input
              id={id}
              type="password"
              autoComplete="current-password"
              required
              value={pw.current}
              onChange={(e) => setPw({ ...pw, current: e.target.value })}
            />
          )}
        </Field>
        <Field label="New password" hint="At least 8 characters">
          {(id) => (
            <Input
              id={id}
              type="password"
              autoComplete="new-password"
              minLength={8}
              required
              value={pw.next}
              onChange={(e) => setPw({ ...pw, next: e.target.value })}
            />
          )}
        </Field>
        <Field label="Confirm new password">
          {(id) => (
            <Input
              id={id}
              type="password"
              autoComplete="new-password"
              required
              value={pw.confirm}
              onChange={(e) => setPw({ ...pw, confirm: e.target.value })}
            />
          )}
        </Field>
        {pwError && (
          <p role="alert" className="text-sm text-critical-text">
            {pwError}
          </p>
        )}
        <Button type="submit" variant="primary" loading={change.isPending}>
          Change password
        </Button>
      </form>
    </Card>
  );
}

export function SettingsPage() {
  const info = useSystemInfo();
  const stats = useSystemStats();
  const s = stats.data;
  return (
    <>
      <PageHeader
        title="Settings"
        description="Your account, system configuration and monitoring overhead."
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <ProfileCard />
        <Card title="System" description="Configured through NETMON_* environment variables">
          {!info.data ? (
            <Spinner />
          ) : (
            <dl className="divide-y divide-line">
              <Row label="Version" value={info.data.version} />
              <Row label="Environment" value={info.data.environment} />
              <Row
                label="Monitoring mode"
                value={
                  <Badge
                    className={
                      info.data.monitor_mode === "simulation" ? "text-warning-text" : undefined
                    }
                  >
                    {info.data.monitor_mode}
                  </Badge>
                }
              />
              <Row label="Engine" value={info.data.monitoring_enabled ? "enabled" : "disabled"} />
              <Row label="Default poll interval" value={`${info.data.poll_interval_seconds}s`} />
              <Row label="Down after" value={`${info.data.down_after_failures} failed polls`} />
              <Row label="Data retention" value={`${info.data.metrics_retention_days} days`} />
              <Row
                label="Webhook notifications"
                value={info.data.notifications.webhook ? "on" : "off"}
              />
              <Row
                label="E-mail notifications"
                value={info.data.notifications.email ? "on" : "off"}
              />
            </dl>
          )}
        </Card>
        <Card
          title="Monitoring overhead"
          description="Cost of monitoring itself - refreshed every 5 s"
        >
          {!s ? (
            <Spinner />
          ) : (
            <dl className="divide-y divide-line">
              <Row label="Engine" value={s.running ? `running (${s.backend})` : "stopped"} />
              <Row label="Monitored devices" value={s.monitored_devices} />
              <Row label="Polls per minute" value={s.poller.polls_per_minute} />
              <Row label="Total polls" value={formatNumber(s.poller.polls_total)} />
              <Row
                label="Avg / max poll time"
                value={`${s.poller.avg_poll_ms.toFixed(1)} / ${s.poller.max_poll_ms.toFixed(0)} ms`}
              />
              <Row label="Probe packets sent" value={formatNumber(s.poller.probe_packets)} />
              <Row label="SNMP requests" value={formatNumber(s.poller.snmp_requests)} />
              <Row
                label="Monitoring traffic (est.)"
                value={`${formatBytes(s.poller.estimated_bytes)} · ${formatBps(s.poller.estimated_bandwidth_bps)}`}
              />
              <Row label="Server process CPU" value={formatPercent(s.process.cpu_percent)} />
              <Row label="Server process memory" value={formatBytes(s.process.rss_bytes)} />
              <Row
                label="Host CPU / memory"
                value={`${formatPercent(s.process.system_cpu_percent, 0)} / ${formatPercent(s.process.system_memory_percent, 0)}`}
              />
              <Row label="Live connections" value={s.websocket_clients} />
              <Row label="Engine uptime" value={formatDuration(s.poller.uptime_seconds)} />
              <Row label="Last poll" value={formatRelative(s.poller.last_poll_at)} />
            </dl>
          )}
        </Card>
      </div>
    </>
  );
}
