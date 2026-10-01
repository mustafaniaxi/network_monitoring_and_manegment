/** Horizontal bar list for ranked magnitudes - one series, one colour, direct labels. */
export function BarList({
  items,
  format = (v) => String(v),
  max,
}: {
  items: { key: string; label: string; value: number; href?: string }[];
  format?: (value: number) => string;
  max?: number;
}) {
  const top = max ?? Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className="space-y-2.5">
      {items.map((item) => (
        <li key={item.key} className="text-xs">
          <div className="mb-1 flex justify-between gap-2">
            <span className="truncate text-ink-2">{item.label}</span>
            <span className="font-medium text-ink tabular-nums">{format(item.value)}</span>
          </div>
          <div className="h-1.5 rounded-full bg-surface-2">
            <div
              className="h-1.5 rounded-full"
              style={{
                width: `${Math.max(2, (item.value / top) * 100)}%`,
                background: "var(--series-1)",
              }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
