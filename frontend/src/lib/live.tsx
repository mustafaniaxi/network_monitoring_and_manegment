/**
 * Live updates over the backend WebSocket (``/api/v1/ws``).
 *
 * Incoming events refresh the relevant React Query caches (throttled, so a burst of samples
 * causes one refetch) and raise toasts for state changes worth interrupting the user for.
 */
import { useQueryClient, type QueryKey } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { getToken } from "@/api/client";
import { keys } from "@/api/hooks";
import type { LiveEvent } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { useToast } from "@/components/ui/Toast";

export type LiveStatus = "connecting" | "open" | "closed";

const LiveContext = createContext<LiveStatus>("closed");

const REFRESH_THROTTLE_MS = 3000;

export function LiveProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [status, setStatus] = useState<LiveStatus>("closed");
  const pending = useRef(new Map<string, { queryKey: QueryKey; exact: boolean }>());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!user) return;
    let socket: WebSocket | null = null;
    let retry = 0;
    let stopped = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    // Collect cache keys to refresh and flush them together, at most every few seconds.
    type Target = { queryKey: QueryKey; exact: boolean };
    const isTarget = (t: QueryKey | Target): t is Target => !Array.isArray(t);
    const schedule = (...targets: (QueryKey | Target)[]) => {
      for (const t of targets) {
        const entry: Target = isTarget(t) ? t : { queryKey: t, exact: false };
        pending.current.set(JSON.stringify(entry), entry);
      }
      if (timer.current) return;
      timer.current = setTimeout(() => {
        const entries = [...pending.current.values()];
        pending.current.clear();
        timer.current = null;
        entries.forEach((e) => queryClient.invalidateQueries(e));
      }, REFRESH_THROTTLE_MS);
    };
    const deviceKeys = (id: unknown) => [
      [...keys.devices, "list"],
      { queryKey: keys.device(Number(id)), exact: true },
      [...keys.dashboard, "summary"],
      keys.topology,
    ];

    const handle = (event: LiveEvent) => {
      const data = event.data ?? {};
      switch (event.type) {
        case "device.sample":
          schedule(...deviceKeys(data.device_id));
          break;
        case "device.status": {
          const name = String(data.name ?? "Device");
          if (data.status === "down") notify("error", `${name} is down`);
          else if (data.status === "up" && data.previous === "down")
            notify("success", `${name} is back up`);
          schedule(...deviceKeys(data.device_id), keys.alerts);
          break;
        }
        case "alert.opened":
          notify(
            data.severity === "critical" ? "error" : "warning",
            String(data.title ?? "Alert"),
            String(data.message ?? ""),
          );
          schedule(
            keys.alerts,
            [...keys.dashboard, "summary"],
            keys.device(Number(data.device_id)),
          );
          break;
        case "alert.resolved":
          schedule(
            keys.alerts,
            [...keys.dashboard, "summary"],
            keys.device(Number(data.device_id)),
          );
          break;
        default:
          break;
      }
    };

    const connect = () => {
      const token = getToken();
      if (!token || stopped) return;
      setStatus("connecting");
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(
        `${proto}://${window.location.host}/api/v1/ws?token=${encodeURIComponent(token)}`,
      );
      socket.onopen = () => {
        retry = 0;
        setStatus("open");
      };
      socket.onmessage = (msg) => {
        try {
          handle(JSON.parse(msg.data as string) as LiveEvent);
        } catch {
          /* ignore malformed frames */
        }
      };
      socket.onclose = () => {
        setStatus("closed");
        if (stopped) return;
        retry += 1;
        const delay = Math.min(30_000, 1000 * 2 ** Math.min(retry, 5));
        reconnectTimer = setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
      setStatus("closed");
    };
  }, [user, queryClient, notify]);

  return <LiveContext.Provider value={status}>{children}</LiveContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useLiveStatus(): LiveStatus {
  return useContext(LiveContext);
}
