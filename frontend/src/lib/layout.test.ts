import { describe, expect, it } from "vitest";

import type { TopologyEdge, TopologyNode } from "@/api/types";
import { autoLayout } from "./layout";

const node = (
  id: number,
  device_type: TopologyNode["device_type"],
  name = `n${id}`,
): TopologyNode => ({
  id,
  name,
  ip_address: `10.0.0.${id}`,
  device_type,
  status: "up",
  is_monitored: true,
  last_latency_ms: 1,
  x: null,
  y: null,
});

const edge = (id: number, source_id: number, target_id: number): TopologyEdge => ({
  id,
  source_id,
  target_id,
  link_type: "ethernet",
  source_interface: null,
  target_interface: null,
  bandwidth_mbps: null,
  description: null,
  status: "up",
});

describe("autoLayout", () => {
  it("ranks devices by hops from the upstream root", () => {
    const nodes = [
      node(1, "server"),
      node(2, "switch"),
      node(3, "router"),
      node(4, "cloud"),
      node(5, "pc"),
    ];
    const edges = [edge(1, 4, 3), edge(2, 3, 2), edge(3, 2, 1), edge(4, 2, 5)];
    const pos = autoLayout(nodes, edges);
    const y = (id: number) => pos.get(id)!.y;
    expect(y(4)).toBeLessThan(y(3)); // cloud above router
    expect(y(3)).toBeLessThan(y(2)); // router above switch
    expect(y(1)).toBe(y(5)); // leaves share a row
    expect(pos.get(1)!.x).not.toBe(pos.get(5)!.x);
  });

  it("places unlinked devices on their own last row", () => {
    const nodes = [node(1, "router"), node(2, "switch"), node(3, "printer")];
    const pos = autoLayout(nodes, [edge(1, 1, 2)]);
    expect(pos.get(3)!.y).toBeGreaterThan(pos.get(2)!.y);
  });
});
