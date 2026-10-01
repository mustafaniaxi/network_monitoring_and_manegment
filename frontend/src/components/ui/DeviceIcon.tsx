import {
  Cloud,
  HardDrive,
  Laptop,
  Network,
  Printer,
  Router,
  Server,
  Shield,
  Wifi,
  type LucideProps,
} from "lucide-react";

import type { DeviceType } from "@/api/types";

const ICONS: Record<DeviceType, typeof Router> = {
  router: Router,
  switch: Network,
  firewall: Shield,
  server: Server,
  pc: Laptop,
  access_point: Wifi,
  printer: Printer,
  cloud: Cloud,
  other: HardDrive,
};

export function DeviceIcon({ type, ...props }: { type: DeviceType } & LucideProps) {
  const Icon = ICONS[type] ?? HardDrive;
  return <Icon aria-hidden {...props} />;
}
