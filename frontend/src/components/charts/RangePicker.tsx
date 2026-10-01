import type { TimeRange } from "@/api/types";
import { Segmented } from "@/components/ui/Form";

const OPTIONS = [
  { value: "1h", label: "1h" },
  { value: "6h", label: "6h" },
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
] as const satisfies readonly { value: TimeRange; label: string }[];

export function RangePicker({
  value,
  onChange,
}: {
  value: TimeRange;
  onChange: (r: TimeRange) => void;
}) {
  return <Segmented label="Time range" value={value} onChange={onChange} options={OPTIONS} />;
}
