import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/** Stat tile: label, value (proportional figures), optional context line. */
export function StatTile({
  label,
  value,
  sub,
  icon,
  tone,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon?: ReactNode;
  tone?: "good" | "warning" | "critical";
}) {
  return (
    <div className="card flex flex-col gap-1 p-4">
      <div className="flex items-center justify-between text-xs font-medium text-ink-2">
        <span>{label}</span>
        {icon && <span className="text-ink-muted">{icon}</span>}
      </div>
      <div
        className={cn(
          "text-2xl font-semibold tracking-tight",
          tone === "critical" && "text-critical-text",
          tone === "warning" && "text-warning-text",
          tone === "good" && "text-good-text",
        )}
      >
        {value}
      </div>
      {sub && <div className="text-xs text-ink-muted">{sub}</div>}
    </div>
  );
}
