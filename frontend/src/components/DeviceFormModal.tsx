import { useState, type FormEvent } from "react";

import { useSaveDevice } from "@/api/hooks";
import type {
  CheckMethod,
  Device,
  DevicePayload,
  DeviceType,
  SnmpAuthProtocol,
  SnmpPrivProtocol,
  SnmpVersion,
} from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select, Toggle } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { DEVICE_TYPE_LABEL } from "@/lib/format";

interface FormState {
  name: string;
  ip_address: string;
  device_type: DeviceType;
  vendor: string;
  model: string;
  location: string;
  description: string;
  tags: string;
  is_monitored: boolean;
  check_method: CheckMethod;
  tcp_port: string;
  poll_interval_seconds: string;
  snmp_enabled: boolean;
  snmp_version: SnmpVersion;
  snmp_port: string;
  snmp_community: string;
  snmp_v3_username: string;
  snmp_v3_auth_protocol: SnmpAuthProtocol;
  snmp_v3_auth_key: string;
  snmp_v3_priv_protocol: SnmpPrivProtocol;
  snmp_v3_priv_key: string;
}

function initialState(device?: Device): FormState {
  return {
    name: device?.name ?? "",
    ip_address: device?.ip_address ?? "",
    device_type: device?.device_type ?? "server",
    vendor: device?.vendor ?? "",
    model: device?.model ?? "",
    location: device?.location ?? "",
    description: device?.description ?? "",
    tags: device?.tags.join(", ") ?? "",
    is_monitored: device?.is_monitored ?? true,
    check_method: device?.check_method ?? "icmp",
    tcp_port: device?.tcp_port?.toString() ?? "",
    poll_interval_seconds: device?.poll_interval_seconds?.toString() ?? "",
    snmp_enabled: device?.snmp_enabled ?? false,
    snmp_version: device?.snmp_version ?? "v2c",
    snmp_port: device?.snmp_port?.toString() ?? "161",
    snmp_community: "",
    snmp_v3_username: device?.snmp_v3_username ?? "",
    snmp_v3_auth_protocol: device?.snmp_v3_auth_protocol ?? "sha",
    snmp_v3_auth_key: "",
    snmp_v3_priv_protocol: device?.snmp_v3_priv_protocol ?? "aes128",
    snmp_v3_priv_key: "",
  };
}

const optional = (v: string) => (v.trim() === "" ? null : v.trim());
const optionalInt = (v: string) => (v.trim() === "" ? null : Number(v));

function toPayload(f: FormState, editing: boolean): DevicePayload {
  const payload: DevicePayload = {
    name: f.name.trim(),
    ip_address: f.ip_address.trim(),
    device_type: f.device_type,
    vendor: optional(f.vendor),
    model: optional(f.model),
    location: optional(f.location),
    description: optional(f.description),
    tags: f.tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean),
    is_monitored: f.is_monitored,
    check_method: f.check_method,
    tcp_port: f.check_method === "tcp" ? optionalInt(f.tcp_port) : null,
    poll_interval_seconds: optionalInt(f.poll_interval_seconds),
    snmp_enabled: f.snmp_enabled,
    snmp_version: f.snmp_version,
    snmp_port: Number(f.snmp_port) || 161,
    snmp_v3_username: optional(f.snmp_v3_username),
    snmp_v3_auth_protocol: f.snmp_v3_auth_protocol,
    snmp_v3_priv_protocol: f.snmp_v3_priv_protocol,
  };
  // Secrets are write-only: when editing, an empty field keeps the stored value.
  if (f.snmp_community || !editing) payload.snmp_community = f.snmp_community || undefined;
  if (f.snmp_v3_auth_key) payload.snmp_v3_auth_key = f.snmp_v3_auth_key;
  if (f.snmp_v3_priv_key) payload.snmp_v3_priv_key = f.snmp_v3_priv_key;
  return payload;
}

export function DeviceFormModal({
  open,
  device,
  onClose,
}: {
  open: boolean;
  device?: Device;
  onClose: () => void;
}) {
  const [form, setForm] = useState<FormState>(() => initialState(device));
  const [error, setError] = useState<string | null>(null);
  const save = useSaveDevice();
  const { notify } = useToast();
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const saved = await save.mutateAsync({ id: device?.id, payload: toPayload(form, !!device) });
      notify(
        "success",
        device ? `${saved.name} updated` : `${saved.name} added`,
        device ? undefined : "First measurement within a few seconds.",
      );
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the device");
    }
  }

  const secretHint = (isSet: boolean | undefined) =>
    device && isSet ? "Stored - leave blank to keep" : undefined;

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title={device ? `Edit ${device.name}` : "Add device"}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" form="device-form" variant="primary" loading={save.isPending}>
            {device ? "Save changes" : "Add device"}
          </Button>
        </>
      }
    >
      <form id="device-form" onSubmit={submit} className="space-y-6">
        <section className="grid gap-4 sm:grid-cols-2">
          <h3 className="text-xs font-semibold tracking-wide text-ink-muted uppercase sm:col-span-2">
            General
          </h3>
          <Field label="Name">
            {(id) => (
              <Input
                id={id}
                required
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder="Web Server"
              />
            )}
          </Field>
          <Field label="IP address or hostname">
            {(id) => (
              <Input
                id={id}
                required
                value={form.ip_address}
                onChange={(e) => set("ip_address", e.target.value)}
                placeholder="192.168.1.10"
              />
            )}
          </Field>
          <Field label="Type">
            {(id) => (
              <Select
                id={id}
                value={form.device_type}
                onChange={(e) => set("device_type", e.target.value as DeviceType)}
              >
                {Object.entries(DEVICE_TYPE_LABEL).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Location">
            {(id) => (
              <Input
                id={id}
                value={form.location}
                onChange={(e) => set("location", e.target.value)}
                placeholder="Server room"
              />
            )}
          </Field>
          <Field label="Vendor">
            {(id) => (
              <Input id={id} value={form.vendor} onChange={(e) => set("vendor", e.target.value)} />
            )}
          </Field>
          <Field label="Model">
            {(id) => (
              <Input id={id} value={form.model} onChange={(e) => set("model", e.target.value)} />
            )}
          </Field>
          <Field label="Tags" hint="Comma separated" className="sm:col-span-2">
            {(id) => (
              <Input
                id={id}
                value={form.tags}
                onChange={(e) => set("tags", e.target.value)}
                placeholder="core, production"
              />
            )}
          </Field>
        </section>

        <section className="grid gap-4 sm:grid-cols-2">
          <h3 className="text-xs font-semibold tracking-wide text-ink-muted uppercase sm:col-span-2">
            Monitoring
          </h3>
          <div className="sm:col-span-2">
            <Toggle
              checked={form.is_monitored}
              onChange={(v) => set("is_monitored", v)}
              label="Monitor this device"
              description="Disable to keep it in the inventory without polling."
            />
          </div>
          <Field
            label="Availability check"
            hint={
              form.check_method === "icmp"
                ? "ICMP echo (ping)"
                : "TCP handshake - for hosts that block ping"
            }
          >
            {(id) => (
              <Select
                id={id}
                value={form.check_method}
                onChange={(e) => set("check_method", e.target.value as CheckMethod)}
              >
                <option value="icmp">ICMP ping</option>
                <option value="tcp">TCP connect</option>
              </Select>
            )}
          </Field>
          {form.check_method === "tcp" ? (
            <Field label="TCP port">
              {(id) => (
                <Input
                  id={id}
                  type="number"
                  min={1}
                  max={65535}
                  required
                  value={form.tcp_port}
                  onChange={(e) => set("tcp_port", e.target.value)}
                  placeholder="443"
                />
              )}
            </Field>
          ) : (
            <div />
          )}
          <Field label="Poll interval (seconds)" hint="Blank = global default">
            {(id) => (
              <Input
                id={id}
                type="number"
                min={5}
                max={3600}
                value={form.poll_interval_seconds}
                onChange={(e) => set("poll_interval_seconds", e.target.value)}
              />
            )}
          </Field>
        </section>

        <section className="grid gap-4 sm:grid-cols-2">
          <h3 className="text-xs font-semibold tracking-wide text-ink-muted uppercase sm:col-span-2">
            SNMP
          </h3>
          <div className="sm:col-span-2">
            <Toggle
              checked={form.snmp_enabled}
              onChange={(v) => set("snmp_enabled", v)}
              label="Collect SNMP metrics"
              description="CPU, memory, interface status and bandwidth."
            />
          </div>
          {form.snmp_enabled && (
            <>
              <Field label="Version">
                {(id) => (
                  <Select
                    id={id}
                    value={form.snmp_version}
                    onChange={(e) => set("snmp_version", e.target.value as SnmpVersion)}
                  >
                    <option value="v2c">v2c</option>
                    <option value="v1">v1</option>
                    <option value="v3">v3 (authenticated)</option>
                  </Select>
                )}
              </Field>
              <Field label="Port">
                {(id) => (
                  <Input
                    id={id}
                    type="number"
                    value={form.snmp_port}
                    onChange={(e) => set("snmp_port", e.target.value)}
                  />
                )}
              </Field>
              {form.snmp_version !== "v3" ? (
                <Field
                  label="Community"
                  hint={secretHint(device?.snmp_community_set) ?? "Default: public"}
                  className="sm:col-span-2"
                >
                  {(id) => (
                    <Input
                      id={id}
                      type="password"
                      autoComplete="off"
                      value={form.snmp_community}
                      onChange={(e) => set("snmp_community", e.target.value)}
                    />
                  )}
                </Field>
              ) : (
                <>
                  <Field label="Username">
                    {(id) => (
                      <Input
                        id={id}
                        value={form.snmp_v3_username}
                        onChange={(e) => set("snmp_v3_username", e.target.value)}
                      />
                    )}
                  </Field>
                  <div />
                  <Field label="Auth protocol">
                    {(id) => (
                      <Select
                        id={id}
                        value={form.snmp_v3_auth_protocol}
                        onChange={(e) =>
                          set("snmp_v3_auth_protocol", e.target.value as SnmpAuthProtocol)
                        }
                      >
                        {["none", "md5", "sha", "sha256", "sha512"].map((p) => (
                          <option key={p} value={p}>
                            {p.toUpperCase()}
                          </option>
                        ))}
                      </Select>
                    )}
                  </Field>
                  <Field label="Auth key" hint={secretHint(device?.snmp_v3_auth_key_set)}>
                    {(id) => (
                      <Input
                        id={id}
                        type="password"
                        autoComplete="off"
                        value={form.snmp_v3_auth_key}
                        onChange={(e) => set("snmp_v3_auth_key", e.target.value)}
                      />
                    )}
                  </Field>
                  <Field label="Privacy protocol">
                    {(id) => (
                      <Select
                        id={id}
                        value={form.snmp_v3_priv_protocol}
                        onChange={(e) =>
                          set("snmp_v3_priv_protocol", e.target.value as SnmpPrivProtocol)
                        }
                      >
                        {["none", "des", "aes128", "aes256"].map((p) => (
                          <option key={p} value={p}>
                            {p.toUpperCase()}
                          </option>
                        ))}
                      </Select>
                    )}
                  </Field>
                  <Field label="Privacy key" hint={secretHint(device?.snmp_v3_priv_key_set)}>
                    {(id) => (
                      <Input
                        id={id}
                        type="password"
                        autoComplete="off"
                        value={form.snmp_v3_priv_key}
                        onChange={(e) => set("snmp_v3_priv_key", e.target.value)}
                      />
                    )}
                  </Field>
                </>
              )}
            </>
          )}
        </section>
        {error && (
          <p role="alert" className="text-sm text-critical-text">
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}
