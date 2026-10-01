import { CircleAlert, CircleCheck, CircleHelp, CircleX, Info, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import type { AlertSeverity, AlertStatus, DeviceStatus } from "@/api/types";
import { cn } from "@/lib/cn";

export function Badge({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border border-line bg-surface-2 px-1.5 py-0.5 text-xs font-medium text-ink-2",
        className,
      )}
    >
      {children}
    </span>
  );
}

// Status colours are reserved for state and always paired with an icon + label.
const STATUS: Record<DeviceStatus, { label: string; icon: typeof CircleCheck; color: string }> = {
  up: { label: "Online", icon: CircleCheck, color: "text-good" },
  degraded: { label: "Degraded", icon: TriangleAlert, color: "text-warning" },
  down: { label: "Offline", icon: CircleX, color: "text-critical" },
  unknown: { label: "Unknown", icon: CircleHelp, color: "text-unknown" },
};

export function StatusBadge({
  status,
  monitored = true,
}: {
  status: DeviceStatus;
  monitored?: boolean;
}) {
  if (!monitored) {
    return (
      <Badge>
        <CircleHelp className="size-3.5 text-unknown" aria-hidden /> Not monitored
      </Badge>
    );
  }
  const s = STATUS[status];
  const Icon = s.icon;
  return (
    <Badge>
      <Icon className={cn("size-3.5", s.color)} aria-hidden />
      {s.label}
    </Badge>
  );
}

export function StatusDot({ status }: { status: DeviceStatus }) {
  const color = {
    up: "bg-good",
    degraded: "bg-warning",
    down: "bg-critical",
    unknown: "bg-unknown",
  }[status];
  return <span className={cn("inline-block size-2 shrink-0 rounded-full", color)} aria-hidden />;
}

const SEVERITY: Record<AlertSeverity, { icon: typeof Info; color: string; label: string }> = {
  info: { icon: Info, color: "text-accent", label: "Info" },
  warning: { icon: TriangleAlert, color: "text-warning", label: "Warning" },
  critical: { icon: CircleAlert, color: "text-critical", label: "Critical" },
};

export function SeverityBadge({ severity }: { severity: AlertSeverity }) {
  const s = SEVERITY[severity];
  const Icon = s.icon;
  return (
    <Badge>
      <Icon className={cn("size-3.5", s.color)} aria-hidden />
      {s.label}
    </Badge>
  );
}

export function AlertStatusBadge({ status }: { status: AlertStatus }) {
  const map = {
    active: { label: "Active", cls: "border-critical/40 text-critical-text" },
    acknowledged: { label: "Acknowledged", cls: "border-warning/50 text-warning-text" },
    resolved: { label: "Resolved", cls: "text-ink-muted" },
  }[status];
  return <Badge className={map.cls}>{map.label}</Badge>;
}
