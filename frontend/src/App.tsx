import { createBrowserRouter } from "react-router";
import { RouterProvider } from "react-router/dom";

import { RequireAdmin, RequireAuth } from "@/auth/RequireAuth";
import { AppShell } from "@/components/layout/AppShell";
import { AlertsPage } from "@/pages/AlertsPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { DeviceDetailPage } from "@/pages/DeviceDetailPage";
import { DevicesPage } from "@/pages/DevicesPage";
import { DiscoveryPage } from "@/pages/DiscoveryPage";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { TopologyPage } from "@/pages/TopologyPage";
import { UsersPage } from "@/pages/UsersPage";

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: "devices", element: <DevicesPage /> },
          { path: "devices/:id", element: <DeviceDetailPage /> },
          { path: "topology", element: <TopologyPage /> },
          { path: "alerts", element: <AlertsPage /> },
          { path: "discovery", element: <DiscoveryPage /> },
          { path: "reports", element: <ReportsPage /> },
          { path: "settings", element: <SettingsPage /> },
          { element: <RequireAdmin />, children: [{ path: "users", element: <UsersPage /> }] },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
]);

export function App() {
  return <RouterProvider router={router} />;
}
