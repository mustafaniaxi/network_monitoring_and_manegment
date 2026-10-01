import {
  Bell,
  ChartColumn,
  LayoutDashboard,
  LogOut,
  Menu,
  Monitor,
  Moon,
  Radar,
  Server,
  Settings,
  Sun,
  Users,
  Waypoints,
  X,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router";

import { useAlertSummary, useSystemInfo } from "@/api/hooks";
import { useAuth } from "@/auth/AuthContext";
import { cn } from "@/lib/cn";
import { useLiveStatus } from "@/lib/live";
import { useTheme, type ThemePreference } from "@/lib/theme";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/devices", label: "Devices", icon: Server },
  { to: "/topology", label: "Topology", icon: Waypoints },
  { to: "/alerts", label: "Alerts", icon: Bell, badge: true },
  { to: "/discovery", label: "Discovery", icon: Radar },
  { to: "/reports", label: "Reports", icon: ChartColumn },
];

function Logo() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
        <rect width="32" height="32" rx="7" fill="var(--accent)" />
        <path
          d="M6 18h4l3-8 4 13 3-9 2 4h4"
          fill="none"
          stroke="#fff"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <div className="leading-tight">
        <p className="text-sm font-semibold">NetMon</p>
        <p className="text-[11px] text-ink-muted">Network monitoring</p>
      </div>
    </div>
  );
}

function NavItem({
  to,
  label,
  icon: Icon,
  end,
  count,
  onNavigate,
}: {
  to: string;
  label: string;
  icon: typeof Server;
  end?: boolean;
  count?: number;
  onNavigate: () => void;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors",
          isActive
            ? "bg-accent-soft text-accent"
            : "text-ink-2 hover:bg-surface-hover hover:text-ink",
        )
      }
    >
      <Icon className="size-4" aria-hidden />
      <span className="flex-1">{label}</span>
      {!!count && (
        <span className="rounded-full bg-critical px-1.5 py-px text-[11px] font-semibold text-white tabular-nums">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </NavLink>
  );
}

function LiveIndicator() {
  const status = useLiveStatus();
  const label = { open: "Live", connecting: "Connecting", closed: "Offline" }[status];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-line px-2 py-0.5 text-xs text-ink-2"
      title={
        status === "open"
          ? "Receiving live updates"
          : "Live updates unavailable - data refreshes periodically"
      }
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          status === "open" ? "bg-good" : status === "connecting" ? "bg-warning" : "bg-unknown",
        )}
        aria-hidden
      />
      {label}
    </span>
  );
}

const THEMES: { value: ThemePreference; icon: typeof Sun; label: string }[] = [
  { value: "light", icon: Sun, label: "Light theme" },
  { value: "dark", icon: Moon, label: "Dark theme" },
  { value: "system", icon: Monitor, label: "System theme" },
];

function ThemeSwitcher() {
  const [theme, setTheme] = useTheme();
  return (
    <div className="flex rounded-lg border border-line p-0.5" role="radiogroup" aria-label="Theme">
      {THEMES.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          role="radio"
          aria-checked={theme === value}
          aria-label={label}
          title={label}
          onClick={() => setTheme(value)}
          className={cn(
            "rounded-md p-1.5 text-ink-muted hover:text-ink",
            theme === value && "bg-surface-hover text-ink",
          )}
        >
          <Icon className="size-3.5" />
        </button>
      ))}
    </div>
  );
}

export function AppShell() {
  const { user, logout, isAdmin } = useAuth();
  const { data: alerts } = useAlertSummary();
  const { data: info } = useSystemInfo();
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

  const nav = [
    ...NAV,
    ...(isAdmin ? [{ to: "/users", label: "Users", icon: Users }] : []),
    { to: "/settings", label: "Settings", icon: Settings },
  ];

  return (
    <div className="flex h-full">
      {open && (
        <div className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={close} aria-hidden />
      )}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-line bg-surface px-3 py-4 transition-transform lg:static lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
        aria-label="Main navigation"
      >
        <div className="mb-6 flex items-center justify-between">
          <Logo />
          <button
            onClick={close}
            className="rounded p-1 text-ink-muted lg:hidden"
            aria-label="Close menu"
          >
            <X className="size-4" />
          </button>
        </div>
        <nav className="flex flex-1 flex-col gap-0.5">
          {nav.map((item) => (
            <NavItem
              key={item.to}
              {...item}
              count={"badge" in item && item.badge ? alerts?.active : undefined}
              onNavigate={close}
            />
          ))}
        </nav>
        {info && (
          <p className="px-2.5 text-[11px] text-ink-muted">
            v{info.version} · {info.monitor_mode === "simulation" ? "simulation" : "live"} mode
          </p>
        )}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-surface px-4">
          <button
            onClick={() => setOpen(true)}
            className="rounded p-1 text-ink-2 lg:hidden"
            aria-label="Open menu"
          >
            <Menu className="size-5" />
          </button>
          <LiveIndicator />
          {info?.monitor_mode === "simulation" && (
            <span
              className="hidden rounded-full border border-warning/50 px-2 py-0.5 text-xs text-warning-text sm:inline"
              title="Measurements are synthetic (NETMON_MONITOR_MODE=simulation)"
            >
              Simulated data
            </span>
          )}
          <div className="ml-auto flex items-center gap-3">
            <ThemeSwitcher />
            <div className="hidden text-right leading-tight sm:block">
              <p className="text-sm font-medium">{user?.full_name || user?.email}</p>
              <p className="text-[11px] text-ink-muted capitalize">{user?.role}</p>
            </div>
            <button
              onClick={logout}
              className="rounded-lg p-2 text-ink-muted hover:bg-surface-hover hover:text-ink"
              aria-label="Sign out"
              title="Sign out"
            >
              <LogOut className="size-4" />
            </button>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
