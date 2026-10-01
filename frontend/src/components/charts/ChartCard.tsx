import { ChartLine, Table2 } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import type { Series } from "./TimeSeriesChart";

/**
 * A chart with a table-view twin: every value is reachable without hovering, which is the
 * accessible equivalent of the visual (WCAG). Refetches keep the previous render dimmed.
 */
export function ChartCard<T extends { ts: string }>({
  title,
  description,
  data,
  series,
  format,
  children,
  fetching,
  className,
}: {
  title: string;
  description?: string;
  data: T[];
  series: Series[];
  format: (value: number) => string;
  children: ReactNode;
  fetching?: boolean;
  className?: string;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const rows = data.filter((d) =>
    series.some((s) => typeof (d as Record<string, unknown>)[s.key] === "number"),
  );
  return (
    <Card
      title={title}
      description={description}
      className={className}
      actions={
        <div
          className="flex rounded-md border border-line"
          role="group"
          aria-label={`${title} view`}
        >
          {(["chart", "table"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              aria-pressed={view === v}
              aria-label={v === "chart" ? "Show chart" : "Show table"}
              className={cn(
                "p-1.5 text-ink-muted hover:text-ink",
                view === v && "bg-surface-hover text-ink",
              )}
            >
              {v === "chart" ? <ChartLine className="size-3.5" /> : <Table2 className="size-3.5" />}
            </button>
          ))}
        </div>
      }
    >
      <div className={cn("transition-opacity", fetching && "opacity-60")}>
        {view === "chart" ? (
          children
        ) : (
          <div className="max-h-64 overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-surface text-left text-ink-muted">
                <tr>
                  <th className="py-1.5 pr-3 font-medium">Time</th>
                  {series.map((s) => (
                    <th key={s.key} className="py-1.5 pr-3 text-right font-medium">
                      {s.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={series.length + 1} className="py-6 text-center text-ink-muted">
                      No data in this range
                    </td>
                  </tr>
                )}
                {rows
                  .slice()
                  .reverse()
                  .map((row) => (
                    <tr key={row.ts} className="border-t border-line">
                      <td className="py-1.5 pr-3 text-ink-2">{formatDateTime(row.ts)}</td>
                      {series.map((s) => {
                        const v = (row as Record<string, unknown>)[s.key];
                        return (
                          <td key={s.key} className="py-1.5 pr-3 text-right">
                            {typeof v === "number" ? format(v) : "—"}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Card>
  );
}
