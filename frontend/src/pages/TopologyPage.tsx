import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { RotateCcw, Trash2, Waypoints } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";

import {
  useCreateLink,
  useDeleteLink,
  useResetPositions,
  useSavePositions,
  useTopology,
} from "@/api/hooks";
import type { DeviceStatus, TopologyEdge, TopologyNode } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui/Card";
import { DeviceIcon } from "@/components/ui/DeviceIcon";
import { Spinner } from "@/components/ui/Spinner";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/lib/cn";
import { DEVICE_TYPE_LABEL, formatMs } from "@/lib/format";
import { NODE_WIDTH, autoLayout } from "@/lib/layout";

type DeviceNodeData = { device: TopologyNode };
type DeviceNode = Node<DeviceNodeData, "device">;

const STATUS_BAR: Record<DeviceStatus, string> = {
  up: "bg-good",
  degraded: "bg-warning",
  down: "bg-critical",
  unknown: "bg-unknown",
};
const EDGE_COLOR: Record<DeviceStatus, string> = {
  up: "var(--chart-tick)",
  degraded: "var(--warning)",
  down: "var(--critical)",
  unknown: "var(--chart-axis)",
};

function DeviceNodeView({ data, selected }: NodeProps<DeviceNode>) {
  const d = data.device;
  return (
    <div
      className={cn(
        "flex items-center gap-2.5 overflow-hidden rounded-lg border bg-surface py-2 pr-3 shadow-sm",
        selected ? "border-accent ring-2 ring-accent-soft" : "border-line-strong",
      )}
      style={{ width: NODE_WIDTH }}
    >
      <span
        className={cn(
          "h-10 w-1 shrink-0 rounded-r",
          STATUS_BAR[d.is_monitored ? d.status : "unknown"],
        )}
        aria-hidden
      />
      <DeviceIcon type={d.device_type} className="size-4 shrink-0 text-ink-2" />
      <div className="min-w-0 leading-tight">
        <p className="truncate text-xs font-semibold">{d.name}</p>
        <p className="truncate font-mono text-[10px] text-ink-muted">{d.ip_address}</p>
        <p className="text-[10px] text-ink-2">
          {d.status === "down"
            ? "Offline"
            : d.status === "unknown"
              ? "Unknown"
              : formatMs(d.last_latency_ms)}
        </p>
      </div>
      <Handle
        type="target"
        position={Position.Top}
        className="!size-2 !border-surface !bg-ink-muted"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!size-2 !border-surface !bg-ink-muted"
      />
    </div>
  );
}

const nodeTypes = { device: DeviceNodeView };

function toEdge(e: TopologyEdge): Edge {
  const dashed = e.link_type === "wireless" || e.link_type === "vpn";
  return {
    id: String(e.id),
    source: String(e.source_id),
    target: String(e.target_id),
    type: "smoothstep",
    label: e.status === "down" ? "down" : e.link_type === "ethernet" ? undefined : e.link_type,
    labelStyle: { fill: "var(--text-2)", fontSize: 10 },
    labelBgStyle: { fill: "var(--surface)" },
    style: {
      stroke: EDGE_COLOR[e.status],
      strokeWidth: 2,
      strokeDasharray: dashed ? "6 4" : undefined,
    },
    markerEnd: { type: MarkerType.ArrowClosed, color: EDGE_COLOR[e.status], width: 14, height: 14 },
    data: { link: e },
  };
}

export function TopologyPage() {
  const { canEdit } = useAuth();
  const { notify } = useToast();
  const topology = useTopology();
  const createLink = useCreateLink();
  const deleteLink = useDeleteLink();
  const savePositions = useSavePositions();
  const resetPositions = useResetPositions();
  const [nodes, setNodes, onNodesChange] = useNodesState<DeviceNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedNode, setSelectedNode] = useState<TopologyNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);

  const layout = useMemo(() => {
    if (!topology.data) return null;
    return autoLayout(topology.data.nodes, topology.data.edges);
  }, [topology.data]);

  useEffect(() => {
    if (!topology.data || !layout) return;
    setNodes((current) => {
      const existing = new Map(current.map((n) => [n.id, n]));
      return topology.data.nodes.map((d) => {
        const prev = existing.get(String(d.id));
        const auto = layout.get(d.id) ?? { x: 0, y: 0 };
        const position =
          prev?.position ?? (d.x !== null && d.y !== null ? { x: d.x, y: d.y } : auto);
        return {
          id: String(d.id),
          type: "device",
          position,
          data: { device: d },
          selected: prev?.selected,
        };
      });
    });
    setEdges(topology.data.edges.map(toEdge));
  }, [topology.data, layout, setNodes, setEdges]);

  function onConnect(connection: Connection) {
    if (!canEdit || !connection.source || !connection.target) return;
    createLink
      .mutateAsync({
        source_id: Number(connection.source),
        target_id: Number(connection.target),
        link_type: "ethernet",
      })
      .then(
        () => notify("success", "Link created"),
        (err: Error) => notify("error", "Could not link devices", err.message),
      );
  }

  function onNodeDragStop(_: unknown, __: DeviceNode, dragged: DeviceNode[]) {
    if (!canEdit) return;
    savePositions.mutate(
      dragged.map((n) => ({ device_id: Number(n.id), x: n.position.x, y: n.position.y })),
    );
  }

  async function reset() {
    await resetPositions.mutateAsync();
    if (layout) {
      setNodes((current) =>
        current.map((n) => ({ ...n, position: layout.get(Number(n.id)) ?? n.position })),
      );
    }
    notify("info", "Layout reset to automatic");
  }

  if (topology.isError)
    return <ErrorState error={topology.error} onRetry={() => topology.refetch()} />;

  return (
    <>
      <PageHeader
        title="Network topology"
        description={
          canEdit
            ? "Drag devices to arrange the map; drag from a device's bottom handle to another device to add a link."
            : "Live map of devices and their connections."
        }
        actions={
          canEdit && (
            <>
              {selectedEdge && (
                <Button
                  variant="danger"
                  icon={<Trash2 className="size-4" />}
                  loading={deleteLink.isPending}
                  onClick={() =>
                    deleteLink.mutateAsync(Number(selectedEdge)).then(() => {
                      setSelectedEdge(null);
                      notify("success", "Link removed");
                    })
                  }
                >
                  Remove link
                </Button>
              )}
              <Button
                icon={<RotateCcw className="size-4" />}
                onClick={reset}
                loading={resetPositions.isPending}
              >
                Auto layout
              </Button>
            </>
          )
        }
      />
      <div className="grid gap-4 xl:grid-cols-[1fr_18rem]">
        <div className="card h-[min(72vh,760px)] min-h-[420px] overflow-hidden">
          {!topology.data ? (
            <div className="p-6">
              <Spinner label="Loading topology" />
            </div>
          ) : topology.data.nodes.length === 0 ? (
            <EmptyState
              icon={<Waypoints className="size-8" />}
              title="No devices yet"
              description="Add devices to see them on the map."
            />
          ) : (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeDragStop={onNodeDragStop}
              onNodeClick={(_, n) => {
                setSelectedNode(n.data.device);
                setSelectedEdge(null);
              }}
              onEdgeClick={(_, e) => {
                setSelectedEdge(e.id);
                setSelectedNode(null);
              }}
              onPaneClick={() => {
                setSelectedNode(null);
                setSelectedEdge(null);
              }}
              nodesDraggable={canEdit}
              nodesConnectable={canEdit}
              edgesFocusable
              fitView
              fitViewOptions={{ padding: 0.15, maxZoom: 1.2 }}
              minZoom={0.2}
              proOptions={{ hideAttribution: true }}
            >
              <Background gap={24} size={1} color="var(--chart-grid)" />
              <Controls showInteractive={false} />
              <MiniMap
                pannable
                zoomable
                bgColor="var(--surface-2)"
                maskColor="rgb(0 0 0 / 0.25)"
                nodeColor={(n) => EDGE_COLOR[(n.data as DeviceNodeData).device.status]}
              />
            </ReactFlow>
          )}
        </div>

        <aside className="flex flex-col gap-4">
          <div className="card p-4">
            <h2 className="mb-3 text-sm font-semibold">Legend</h2>
            <ul className="space-y-2 text-xs text-ink-2">
              {(["up", "degraded", "down", "unknown"] as const).map((s) => (
                <li key={s} className="flex items-center gap-2">
                  <StatusBadge status={s} />
                </li>
              ))}
              <li className="flex items-center gap-2 pt-1">
                <svg width="28" height="6" aria-hidden>
                  <line x1="0" y1="3" x2="28" y2="3" stroke="var(--chart-tick)" strokeWidth="2" />
                </svg>
                Wired link
              </li>
              <li className="flex items-center gap-2">
                <svg width="28" height="6" aria-hidden>
                  <line
                    x1="0"
                    y1="3"
                    x2="28"
                    y2="3"
                    stroke="var(--chart-tick)"
                    strokeWidth="2"
                    strokeDasharray="6 4"
                  />
                </svg>
                Wireless / VPN
              </li>
              <li className="flex items-center gap-2">
                <svg width="28" height="6" aria-hidden>
                  <line x1="0" y1="3" x2="28" y2="3" stroke="var(--critical)" strokeWidth="2" />
                </svg>
                Link with an offline end
              </li>
            </ul>
          </div>
          {selectedNode && (
            <div className="card p-4">
              <div className="mb-2 flex items-center gap-2">
                <DeviceIcon type={selectedNode.device_type} className="size-4 text-ink-2" />
                <h2 className="truncate text-sm font-semibold">{selectedNode.name}</h2>
              </div>
              <dl className="space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <dt className="text-ink-muted">Address</dt>
                  <dd className="font-mono">{selectedNode.ip_address}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-muted">Type</dt>
                  <dd>{DEVICE_TYPE_LABEL[selectedNode.device_type]}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-muted">Latency</dt>
                  <dd>{formatMs(selectedNode.last_latency_ms)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-muted">Status</dt>
                  <dd>
                    <StatusBadge
                      status={selectedNode.status}
                      monitored={selectedNode.is_monitored}
                    />
                  </dd>
                </div>
              </dl>
              <Link
                to={`/devices/${selectedNode.id}`}
                className="mt-3 inline-block text-xs font-medium text-accent hover:underline"
              >
                Open device →
              </Link>
            </div>
          )}
        </aside>
      </div>
    </>
  );
}
