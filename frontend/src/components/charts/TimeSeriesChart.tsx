import { useId } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatDateTime, formatTick } from "@/lib/format";

export interface Series {
  key: string;
  label: string;
  /** CSS colour, normally a categorical token such as var(--series-1). */
  color: string;
}

interface Props<T extends { ts: string }> {
  data: T[];
  series: Series[];
  format: (value: number) => string;
  axisFormat?: (value: number) => string;
  rangeSeconds: number;
  height?: number;
  domain?: [number | "auto" | "dataMin", number | "auto" | "dataMax"];
  variant?: "line" | "area";
}

interface TooltipPayload {
  dataKey?: string | number;
  value?: number | string | null;
  color?: string;
}

function ChartTooltip({
  active,
  payload,
  label,
  series,
  format,
}: {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: string | number;
  series: Series[];
  format: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="card min-w-40 px-3 py-2 text-xs shadow-lg">
      <p className="mb-1.5 text-ink-muted">{formatDateTime(String(label))}</p>
      <ul className="space-y-1">
        {series.map((s) => {
          const entry = payload.find((p) => p.dataKey === s.key);
          const value = entry?.value;
          return (
            <li key={s.key} className="flex items-center gap-2">
              <span
                className="h-0.5 w-3 rounded-full"
                style={{ background: s.color }}
                aria-hidden
              />
              <span className="font-semibold text-ink tabular-nums">
                {typeof value === "number" ? format(value) : "no data"}
              </span>
              <span className="text-ink-2">{s.label}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function Legend({ series }: { series: Series[] }) {
  if (series.length < 2) return null;
  return (
    <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2" aria-label="Legend">
      {series.map((s) => (
        <li key={s.key} className="flex items-center gap-1.5">
          <span className="h-0.5 w-3.5 rounded-full" style={{ background: s.color }} aria-hidden />
          {s.label}
        </li>
      ))}
    </ul>
  );
}

/**
 * Time-series line/area chart: one y-axis, hairline horizontal grid, 2px strokes, crosshair
 * tooltip listing every series. Gaps (missing buckets) are drawn as gaps, not interpolated.
 */
export function TimeSeriesChart<T extends { ts: string }>({
  data,
  series,
  format,
  axisFormat,
  rangeSeconds,
  height = 220,
  domain = [0, "auto"],
  variant = "line",
}: Props<T>) {
  const gradientId = useId().replace(/:/g, "");
  const common = {
    data,
    margin: { top: 6, right: 8, bottom: 0, left: 0 },
  };
  const axes = (
    <>
      <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
      <XAxis
        dataKey="ts"
        tickFormatter={(v: string) => formatTick(v, rangeSeconds)}
        stroke="var(--chart-axis)"
        tick={{ fill: "var(--chart-tick)", fontSize: 11 }}
        tickLine={false}
        minTickGap={48}
      />
      <YAxis
        width={56}
        domain={domain}
        tickFormatter={(v: number) => (axisFormat ?? format)(v)}
        stroke="var(--chart-axis)"
        tick={{ fill: "var(--chart-tick)", fontSize: 11 }}
        tickLine={false}
        axisLine={false}
      />
      <Tooltip
        cursor={{ stroke: "var(--chart-tick)", strokeWidth: 1 }}
        content={(props) => (
          <ChartTooltip
            active={props.active}
            payload={props.payload as unknown as TooltipPayload[] | undefined}
            label={props.label as string | undefined}
            series={series}
            format={format}
          />
        )}
        isAnimationActive={false}
      />
    </>
  );
  const activeDot = { r: 4, strokeWidth: 2, stroke: "var(--surface)" };

  return (
    <div>
      <Legend series={series} />
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          {variant === "area" ? (
            <AreaChart {...common}>
              <defs>
                {series.map((s, i) => (
                  <linearGradient key={s.key} id={`${gradientId}-${i}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={s.color} stopOpacity={0.22} />
                    <stop offset="100%" stopColor={s.color} stopOpacity={0.02} />
                  </linearGradient>
                ))}
              </defs>
              {axes}
              {series.map((s, i) => (
                <Area
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.label}
                  stroke={s.color}
                  strokeWidth={2}
                  fill={`url(#${gradientId}-${i})`}
                  connectNulls={false}
                  dot={false}
                  activeDot={activeDot}
                  isAnimationActive={false}
                />
              ))}
            </AreaChart>
          ) : (
            <LineChart {...common}>
              {axes}
              {series.map((s) => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.label}
                  stroke={s.color}
                  strokeWidth={2}
                  connectNulls={false}
                  dot={false}
                  activeDot={activeDot}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
