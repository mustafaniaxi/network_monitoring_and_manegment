import { formatBps } from "@/lib/format";

const RAMP = ["--seq-0", "--seq-1", "--seq-2", "--seq-3", "--seq-4", "--seq-5", "--seq-6"];

/**
 * Weekday x hour heatmap on a single-hue sequential ramp (light = quiet, dark = busy).
 * Each cell is focusable and carries its value in a native tooltip + aria-label.
 */
export function TrafficHeatmapGrid({
  days,
  matrix,
}: {
  days: string[];
  matrix: (number | null)[][];
}) {
  const values = matrix.flat().filter((v): v is number => v !== null);
  const max = Math.max(1, ...values);
  const step = (v: number) => Math.min(RAMP.length - 1, Math.floor((v / max) * RAMP.length));

  return (
    <div className="overflow-x-auto">
      <div
        className="inline-grid min-w-full gap-[2px]"
        style={{ gridTemplateColumns: "2.5rem repeat(24, minmax(1.1rem, 1fr))" }}
      >
        <span />
        {Array.from({ length: 24 }, (_, h) => (
          <span key={h} className="text-center text-[10px] text-ink-muted tabular-nums">
            {h % 3 === 0 ? h : ""}
          </span>
        ))}
        {days.map((day, d) => (
          <div key={day} className="contents">
            <span className="pr-1 text-right text-[11px] leading-5 text-ink-2">{day}</span>
            {matrix[d].map((v, h) => {
              const label = `${day} ${String(h).padStart(2, "0")}:00 — ${v === null ? "no data" : formatBps(v)}`;
              return (
                <span
                  key={h}
                  tabIndex={0}
                  title={label}
                  aria-label={label}
                  className="h-5 rounded-[3px] outline-offset-1 hover:ring-2 hover:ring-ink/40 focus:ring-2 focus:ring-ink/40"
                  style={{
                    background: v === null ? "var(--surface-2)" : `var(${RAMP[step(v)]})`,
                  }}
                />
              );
            })}
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-2 text-[11px] text-ink-muted">
        <span>Quiet</span>
        <div className="flex gap-[2px]">
          {RAMP.map((r) => (
            <span key={r} className="h-2.5 w-5 rounded-[2px]" style={{ background: `var(${r})` }} />
          ))}
        </div>
        <span>Busy (max {formatBps(max)})</span>
      </div>
    </div>
  );
}
