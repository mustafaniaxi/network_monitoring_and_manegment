// Types mirroring the backend's Pydantic schemas (see backend/netmon/schemas).

export type UserRole = "admin" | "operator" | "viewer";
export type DeviceType =
  | "router"
  | "switch"
  | "firewall"
  | "server"
  | "pc"
  | "access_point"
  | "printer"
  | "cloud"
  | "other";
export type DeviceStatus = "up" | "degraded" | "down" | "unknown";
export type CheckMethod = "icmp" | "tcp";
export type SnmpVersion = "v1" | "v2c" | "v3";
export type SnmpAuthProtocol = "none" | "md5" | "sha" | "sha256" | "sha512";
export type SnmpPrivProtocol = "none" | "des" | "aes128" | "aes256";
export type LinkType = "ethernet" | "fiber" | "wireless" | "vpn" | "wan";
export type AlertMetric =
  | "device_down"
  | "latency_ms"
  | "packet_loss"
  | "cpu_percent"
  | "memory_percent"
  | "bandwidth_util";
export type AlertOperator = "gt" | "gte" | "lt" | "lte";
export type AlertSeverity = "info" | "warning" | "critical";
export type AlertStatus = "active" | "acknowledged" | "resolved";
export type TimeRange = "1h" | "6h" | "24h" | "7d" | "30d";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Device {
  id: number;
  name: string;
  ip_address: string;
  device_type: DeviceType;
  vendor: string | null;
  model: string | null;
  location: string | null;
  description: string | null;
  mac_address: string | null;
  tags: string[];
  is_monitored: boolean;
  poll_interval_seconds: number | null;
  check_method: CheckMethod;
  tcp_port: number | null;
  snmp_enabled: boolean;
  snmp_version: SnmpVersion;
  snmp_port: number;
  snmp_v3_username: string | null;
  snmp_v3_auth_protocol: SnmpAuthProtocol;
  snmp_v3_priv_protocol: SnmpPrivProtocol;
  snmp_community_set: boolean;
  snmp_v3_auth_key_set: boolean;
  snmp_v3_priv_key_set: boolean;
  status: DeviceStatus;
  status_changed_at: string | null;
  last_checked_at: string | null;
  last_seen_at: string | null;
  consecutive_failures: number;
  last_latency_ms: number | null;
  last_packet_loss: number | null;
  last_cpu_percent: number | null;
  last_memory_percent: number | null;
  last_in_bps: number | null;
  last_out_bps: number | null;
  last_bandwidth_util: number | null;
  last_error: string | null;
  sys_name: string | null;
  sys_descr: string | null;
  uptime_seconds: number | null;
  created_at: string;
  updated_at: string;
}

export type DevicePayload = Partial<
  Omit<
    Device,
    | "id"
    | "status"
    | "status_changed_at"
    | "last_checked_at"
    | "last_seen_at"
    | "consecutive_failures"
    | "created_at"
    | "updated_at"
    | `last_${string}`
    | `sys_${string}`
    | "uptime_seconds"
    | `snmp_${string}_set`
  >
> & {
  snmp_community?: string;
  snmp_v3_auth_key?: string;
  snmp_v3_priv_key?: string;
};

export interface Interface {
  id: number;
  if_index: number;
  name: string;
  alias: string | null;
  if_type: number | null;
  admin_status: string;
  oper_status: string;
  speed_mbps: number | null;
  in_bps: number | null;
  out_bps: number | null;
  utilization_percent: number | null;
  updated_at: string | null;
}

export interface MetricPoint {
  ts: string;
  latency_ms: number | null;
  latency_max_ms: number | null;
  jitter_ms: number | null;
  packet_loss: number | null;
  availability: number | null;
  cpu_percent: number | null;
  memory_percent: number | null;
  in_bps: number | null;
  out_bps: number | null;
  bandwidth_util: number | null;
  samples: number;
}

export interface DeviceMetrics {
  device_id: number;
  range: TimeRange;
  bucket_seconds: number;
  points: MetricPoint[];
}

export interface Alert {
  id: number;
  device_id: number;
  device_name: string | null;
  rule_id: number | null;
  metric: AlertMetric;
  severity: AlertSeverity;
  status: AlertStatus;
  title: string;
  message: string;
  value: number | null;
  threshold: number | null;
  triggered_at: string;
  first_breach_at: string | null;
  acknowledged_at: string | null;
  acknowledged_by_id: number | null;
  resolved_at: string | null;
  resolution_note: string | null;
}

export interface AlertSummary {
  active: number;
  acknowledged: number;
  resolved_24h: number;
  by_severity: Record<AlertSeverity, number>;
}

export interface AlertRule {
  id: number;
  name: string;
  description: string | null;
  metric: AlertMetric;
  operator: AlertOperator;
  threshold: number;
  consecutive: number;
  severity: AlertSeverity;
  device_type: DeviceType | null;
  device_id: number | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export type AlertRulePayload = Omit<AlertRule, "id" | "created_at" | "updated_at">;

export interface Link {
  id: number;
  source_id: number;
  target_id: number;
  link_type: LinkType;
  source_interface: string | null;
  target_interface: string | null;
  bandwidth_mbps: number | null;
  description: string | null;
}

export interface TopologyNode {
  id: number;
  name: string;
  ip_address: string;
  device_type: DeviceType;
  status: DeviceStatus;
  is_monitored: boolean;
  last_latency_ms: number | null;
  x: number | null;
  y: number | null;
}

export interface TopologyEdge extends Link {
  status: DeviceStatus;
}

export interface Topology {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

export interface DiscoveredHost {
  ip_address: string;
  latency_ms: number | null;
  hostname: string | null;
  sys_name: string | null;
  sys_descr: string | null;
  suggested_type: DeviceType;
  existing_device_id: number | null;
}

export interface ScanJob {
  id: string;
  cidr: string;
  method: CheckMethod;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  total: number;
  scanned: number;
  found: number;
  created_by: string;
  created_at: string;
  finished_at: string | null;
  error: string | null;
  hosts: DiscoveredHost[];
}

export interface DashboardSummary {
  devices: {
    total: number;
    unmonitored: number;
    up: number;
    down: number;
    degraded: number;
    unknown: number;
  };
  by_type: Partial<Record<DeviceType, number>>;
  availability_24h: number | null;
  samples_24h: number;
  avg_latency_ms_1h: number | null;
  avg_packet_loss_1h: number | null;
  throughput_bps: number;
  avg_bandwidth_util: number | null;
  alerts: {
    active: number;
    acknowledged: number;
    info: number;
    warning: number;
    critical: number;
  };
}

export interface NetworkPoint {
  ts: string;
  latency_ms: number | null;
  packet_loss: number | null;
  availability: number | null;
  in_bps: number | null;
  out_bps: number | null;
  devices: number;
}

export interface NetworkSeries {
  range: TimeRange;
  bucket_seconds: number;
  points: NetworkPoint[];
}

export interface AvailabilityRow {
  device_id: number;
  name: string;
  ip_address: string;
  device_type: DeviceType;
  status: DeviceStatus;
  samples: number;
  availability: number | null;
  avg_latency_ms: number | null;
  max_latency_ms: number | null;
  avg_packet_loss: number | null;
  avg_jitter_ms: number | null;
  incidents: number;
  downtime_seconds: number;
  mttr_seconds: number | null;
}

export interface TrafficHeatmap {
  days: string[];
  matrix_bps: (number | null)[][];
  peak: { day: number; hour: number; bps: number } | null;
}

export interface Bottlenecks {
  devices: {
    device_id: number;
    name: string;
    device_type: DeviceType;
    avg_bandwidth_util: number | null;
    max_bandwidth_util: number | null;
    avg_cpu_percent: number | null;
    max_cpu_percent: number | null;
    avg_latency_ms: number | null;
    avg_packet_loss: number | null;
  }[];
  interfaces: {
    device_id: number;
    device: string | null;
    interface: string;
    speed_mbps: number | null;
    in_bps: number | null;
    out_bps: number | null;
    utilization_percent: number | null;
  }[];
}

export interface DegradationRow {
  device_id: number;
  name: string;
  latency_before_ms: number | null;
  latency_after_ms: number | null;
  latency_change_percent: number | null;
  packet_loss_before: number | null;
  packet_loss_after: number | null;
  availability_before: number | null;
  availability_after: number | null;
  degraded: boolean;
}

export interface Distribution {
  count: number;
  mean: number | null;
  median: number | null;
  min: number | null;
  max: number | null;
}

export interface DetectionReport {
  outages: number;
  detection_delay_seconds: Distribution;
  time_to_recovery_seconds: Distribution;
}

export interface SystemInfo {
  name: string;
  version: string;
  environment: string;
  monitor_mode: "live" | "simulation";
  monitoring_enabled: boolean;
  poll_interval_seconds: number;
  down_after_failures: number;
  metrics_retention_days: number;
  notifications: { webhook: boolean; email: boolean };
}

export interface SystemStats {
  running: boolean;
  backend: string;
  monitored_devices: number;
  in_flight: number;
  websocket_clients: number;
  poller: {
    started_at: string;
    uptime_seconds: number;
    polls_total: number;
    polls_down: number;
    poll_errors: number;
    probe_packets: number;
    snmp_requests: number;
    estimated_bytes: number;
    estimated_bandwidth_bps: number;
    polls_per_minute: number;
    avg_poll_ms: number;
    max_poll_ms: number;
    last_poll_at: string | null;
  };
  process: {
    pid: number;
    cpu_percent: number;
    rss_bytes: number;
    threads: number;
    system_cpu_percent: number;
    system_memory_percent: number;
  };
}

export interface LiveEvent {
  type: "hello" | "ping" | "device.sample" | "device.status" | "alert.opened" | "alert.resolved";
  ts?: string;
  data?: Record<string, unknown>;
}
