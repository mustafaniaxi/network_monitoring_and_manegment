/** TanStack Query hooks - one place that knows every endpoint and cache key. */
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";

import { request } from "./client";
import type {
  Alert,
  AlertRule,
  AlertRulePayload,
  AlertSeverity,
  AlertStatus,
  AlertSummary,
  AvailabilityRow,
  Bottlenecks,
  DashboardSummary,
  DegradationRow,
  DetectionReport,
  Device,
  DeviceMetrics,
  DevicePayload,
  DeviceStatus,
  DeviceType,
  Interface,
  Link,
  NetworkSeries,
  Page,
  ScanJob,
  SystemInfo,
  SystemStats,
  TimeRange,
  Topology,
  TrafficHeatmap,
  User,
  UserRole,
} from "./types";

export const keys = {
  devices: ["devices"] as const,
  device: (id: number) => ["devices", "one", id] as const,
  alerts: ["alerts"] as const,
  rules: ["alert-rules"] as const,
  topology: ["topology"] as const,
  dashboard: ["dashboard"] as const,
  reports: ["reports"] as const,
  users: ["users"] as const,
  scans: ["scans"] as const,
  system: ["system"] as const,
};

function useInvalidate() {
  const qc = useQueryClient();
  return (...queryKeys: QueryKey[]) =>
    Promise.all(queryKeys.map((queryKey) => qc.invalidateQueries({ queryKey })));
}

// ---------------------------------------------------------------- devices
export interface DeviceQuery {
  search?: string;
  status?: DeviceStatus | "";
  device_type?: DeviceType | "";
  page?: number;
  page_size?: number;
  sort?: string;
}

export function useDevices(params: DeviceQuery = {}) {
  return useQuery({
    queryKey: [...keys.devices, "list", params],
    queryFn: () => request<Page<Device>>("/devices", { query: { ...params } }),
    placeholderData: keepPreviousData,
  });
}

/** Every device (for pickers). The API caps page_size at 500. */
export function useAllDevices() {
  return useQuery({
    queryKey: [...keys.devices, "all"],
    queryFn: () => request<Page<Device>>("/devices", { query: { page_size: 500 } }),
    select: (page) => page.items,
  });
}

export function useDevice(id: number) {
  return useQuery({
    queryKey: keys.device(id),
    queryFn: () => request<Device>(`/devices/${id}`),
  });
}

export function useDeviceMetrics(id: number, range: TimeRange) {
  return useQuery({
    queryKey: [...keys.device(id), "metrics", range],
    queryFn: () => request<DeviceMetrics>(`/devices/${id}/metrics`, { query: { range } }),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });
}

export function useDeviceInterfaces(id: number) {
  return useQuery({
    queryKey: [...keys.device(id), "interfaces"],
    queryFn: () => request<Interface[]>(`/devices/${id}/interfaces`),
    refetchInterval: 30_000,
  });
}

export function useDeviceAlerts(id: number) {
  return useQuery({
    queryKey: [...keys.device(id), "alerts"],
    queryFn: () => request<Alert[]>(`/devices/${id}/alerts`, { query: { limit: 25 } }),
  });
}

export function useSaveDevice() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, payload }: { id?: number; payload: DevicePayload }) =>
      id
        ? request<Device>(`/devices/${id}`, { method: "PATCH", body: payload })
        : request<Device>("/devices", { method: "POST", body: payload }),
    onSuccess: () => invalidate(keys.devices, keys.dashboard, keys.topology),
  });
}

export function useDeleteDevice() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: number) => request<void>(`/devices/${id}`, { method: "DELETE" }),
    onSuccess: () => invalidate(keys.devices, keys.dashboard, keys.topology, keys.alerts),
  });
}

export function useCheckDevice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => request<Device>(`/devices/${id}/check`, { method: "POST" }),
    onSuccess: (device) => {
      qc.setQueryData(keys.device(device.id), device);
      return qc.invalidateQueries({ queryKey: keys.devices });
    },
  });
}

// ---------------------------------------------------------------- alerts
export interface AlertQuery {
  status?: AlertStatus[];
  severity?: AlertSeverity[];
  device_id?: number;
  open_only?: boolean;
  page?: number;
  page_size?: number;
}

export function useAlerts(params: AlertQuery = {}) {
  return useQuery({
    queryKey: [...keys.alerts, "list", params],
    queryFn: () => request<Page<Alert>>("/alerts", { query: { ...params } }),
    placeholderData: keepPreviousData,
  });
}

export function useAlertSummary() {
  return useQuery({
    queryKey: [...keys.alerts, "summary"],
    queryFn: () => request<AlertSummary>("/alerts/summary"),
  });
}

export function useAlertAction() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({
      id,
      action,
      note,
    }: {
      id: number;
      action: "acknowledge" | "resolve";
      note?: string;
    }) => request<Alert>(`/alerts/${id}/${action}`, { method: "POST", body: { note } }),
    onSuccess: () => invalidate(keys.alerts, keys.dashboard, keys.devices),
  });
}

export function useAlertRules() {
  return useQuery({ queryKey: keys.rules, queryFn: () => request<AlertRule[]>("/alert-rules") });
}

export function useSaveRule() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, payload }: { id?: number; payload: Partial<AlertRulePayload> }) =>
      id
        ? request<AlertRule>(`/alert-rules/${id}`, { method: "PATCH", body: payload })
        : request<AlertRule>("/alert-rules", { method: "POST", body: payload }),
    onSuccess: () => invalidate(keys.rules, keys.alerts),
  });
}

export function useDeleteRule() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: number) => request<void>(`/alert-rules/${id}`, { method: "DELETE" }),
    onSuccess: () => invalidate(keys.rules, keys.alerts),
  });
}

// ---------------------------------------------------------------- topology
export function useTopology() {
  return useQuery({
    queryKey: keys.topology,
    queryFn: () => request<Topology>("/topology"),
    refetchInterval: 30_000,
  });
}

export function useCreateLink() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (payload: Pick<Link, "source_id" | "target_id"> & Partial<Link>) =>
      request<Link>("/topology/links", { method: "POST", body: payload }),
    onSuccess: () => invalidate(keys.topology),
  });
}

export function useDeleteLink() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: number) => request<void>(`/topology/links/${id}`, { method: "DELETE" }),
    onSuccess: () => invalidate(keys.topology),
  });
}

export function useSavePositions() {
  return useMutation({
    mutationFn: (positions: { device_id: number; x: number; y: number }[]) =>
      request("/topology/positions", { method: "PUT", body: positions }),
  });
}

export function useResetPositions() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: () => request("/topology/positions", { method: "DELETE" }),
    onSuccess: () => invalidate(keys.topology),
  });
}

// ---------------------------------------------------------------- dashboard & reports
export function useDashboardSummary() {
  return useQuery({
    queryKey: [...keys.dashboard, "summary"],
    queryFn: () => request<DashboardSummary>("/dashboard/summary"),
    refetchInterval: 30_000,
  });
}

export function useNetworkSeries(range: TimeRange) {
  return useQuery({
    queryKey: [...keys.dashboard, "series", range],
    queryFn: () => request<NetworkSeries>("/dashboard/timeseries", { query: { range } }),
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
  });
}

function useReport<T>(name: string, range: TimeRange, extra: Record<string, number> = {}) {
  return useQuery({
    queryKey: [...keys.reports, name, range, extra],
    queryFn: () => request<T>(`/reports/${name}`, { query: { range, ...extra } }),
    placeholderData: keepPreviousData,
  });
}

export const useAvailabilityReport = (range: TimeRange) =>
  useReport<AvailabilityRow[]>("availability", range);
export const useTopFailing = (range: TimeRange) =>
  useReport<AvailabilityRow[]>("top-failing", range, { limit: 5 });
export const useTrafficHeatmap = (range: TimeRange) =>
  useReport<TrafficHeatmap>("traffic-heatmap", range, {
    tz_offset_minutes: -new Date().getTimezoneOffset(),
  });
export const useBottlenecks = (range: TimeRange) => useReport<Bottlenecks>("bottlenecks", range);
export const useDegradation = (range: TimeRange) =>
  useReport<DegradationRow[]>("degradation", range);
export const useDetectionReport = (range: TimeRange) =>
  useReport<DetectionReport>("detection", range);

// ---------------------------------------------------------------- discovery
export function useScans() {
  return useQuery({
    queryKey: keys.scans,
    queryFn: () => request<ScanJob[]>("/discovery/scans"),
    refetchInterval: (query) =>
      query.state.data?.some((j) => j.status === "running" || j.status === "pending")
        ? 1000
        : false,
  });
}

export function useStartScan() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (payload: {
      cidr: string;
      method: "icmp" | "tcp";
      tcp_port?: number;
      snmp_community?: string;
    }) => request<ScanJob>("/discovery/scans", { method: "POST", body: payload }),
    onSuccess: () => invalidate(keys.scans),
  });
}

export function useImportHosts() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (payload: {
      hosts: { ip_address: string; name: string; device_type: DeviceType }[];
      snmp_enabled: boolean;
      snmp_community?: string;
    }) =>
      request<{ created: number[]; skipped: string[] }>("/discovery/import", {
        method: "POST",
        body: payload,
      }),
    onSuccess: () => invalidate(keys.devices, keys.dashboard, keys.topology, keys.scans),
  });
}

// ---------------------------------------------------------------- users & account
export function useUsers(enabled = true) {
  return useQuery({ queryKey: keys.users, queryFn: () => request<User[]>("/users"), enabled });
}

export interface UserPayload {
  email?: string;
  full_name?: string;
  role?: UserRole;
  is_active?: boolean;
  password?: string;
}

export function useSaveUser() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, payload }: { id?: number; payload: UserPayload }) =>
      id
        ? request<User>(`/users/${id}`, { method: "PATCH", body: payload })
        : request<User>("/users", { method: "POST", body: payload }),
    onSuccess: () => invalidate(keys.users),
  });
}

export function useDeleteUser() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: number) => request<void>(`/users/${id}`, { method: "DELETE" }),
    onSuccess: () => invalidate(keys.users),
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (payload: { current_password: string; new_password: string }) =>
      request<{ detail: string }>("/auth/change-password", { method: "POST", body: payload }),
  });
}

// ---------------------------------------------------------------- system
export function useSystemInfo() {
  return useQuery({
    queryKey: [...keys.system, "info"],
    queryFn: () => request<SystemInfo>("/system/info"),
    staleTime: 5 * 60_000,
  });
}

export function useSystemStats() {
  return useQuery({
    queryKey: [...keys.system, "stats"],
    queryFn: () => request<SystemStats>("/system/stats"),
    refetchInterval: 5_000,
  });
}
