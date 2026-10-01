/**
 * Automatic hierarchical layout for the topology map (no external dependency).
 *
 * Nodes are ranked by breadth-first distance from the "root" of the network - the upstream
 * cloud/internet node if present, otherwise a router, otherwise the best-connected device -
 * and each rank is laid out on its own row. Disconnected devices go to a final row.
 */
import type { TopologyEdge, TopologyNode } from "@/api/types";

export const NODE_WIDTH = 190;
export const NODE_HEIGHT = 64;
const H_GAP = 40;
const V_GAP = 90;

const ROOT_PRIORITY: Record<string, number> = { cloud: 0, firewall: 1, router: 2, switch: 3 };

export function autoLayout(
  nodes: TopologyNode[],
  edges: TopologyEdge[],
): Map<number, { x: number; y: number }> {
  const adjacency = new Map<number, Set<number>>();
  nodes.forEach((n) => adjacency.set(n.id, new Set()));
  edges.forEach((e) => {
    adjacency.get(e.source_id)?.add(e.target_id);
    adjacency.get(e.target_id)?.add(e.source_id);
  });

  const level = new Map<number, number>();
  const connected = nodes.filter((n) => (adjacency.get(n.id)?.size ?? 0) > 0);
  const byPriority = [...connected].sort(
    (a, b) =>
      (ROOT_PRIORITY[a.device_type] ?? 9) - (ROOT_PRIORITY[b.device_type] ?? 9) ||
      (adjacency.get(b.id)?.size ?? 0) - (adjacency.get(a.id)?.size ?? 0) ||
      a.id - b.id,
  );

  // BFS from each not-yet-visited component root; disjoint networks share rows side by side.
  for (const root of byPriority) {
    if (level.has(root.id)) continue;
    level.set(root.id, 0);
    const queue = [root.id];
    while (queue.length) {
      const current = queue.shift()!;
      for (const next of adjacency.get(current) ?? []) {
        if (!level.has(next)) {
          level.set(next, level.get(current)! + 1);
          queue.push(next);
        }
      }
    }
  }
  const isolatedLevel = level.size ? Math.max(...level.values()) + 1 : 0;
  nodes.forEach((n) => {
    if (!level.has(n.id)) level.set(n.id, isolatedLevel);
  });

  const rows = new Map<number, TopologyNode[]>();
  nodes.forEach((n) => {
    const l = level.get(n.id)!;
    rows.set(l, [...(rows.get(l) ?? []), n]);
  });

  const widest = Math.max(1, ...[...rows.values()].map((r) => r.length));
  const totalWidth = widest * (NODE_WIDTH + H_GAP);
  const positions = new Map<number, { x: number; y: number }>();
  [...rows.entries()]
    .sort(([a], [b]) => a - b)
    .forEach(([, row], rowIndex) => {
      row.sort((a, b) => a.name.localeCompare(b.name));
      const rowWidth = row.length * (NODE_WIDTH + H_GAP);
      const offset = (totalWidth - rowWidth) / 2;
      row.forEach((n, i) => {
        positions.set(n.id, {
          x: offset + i * (NODE_WIDTH + H_GAP),
          y: rowIndex * (NODE_HEIGHT + V_GAP),
        });
      });
    });
  return positions;
}
