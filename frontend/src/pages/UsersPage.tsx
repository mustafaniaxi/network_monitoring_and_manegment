import { Pencil, Trash2, UserPlus } from "lucide-react";
import { useState, type FormEvent } from "react";

import { useDeleteUser, useSaveUser, useUsers, type UserPayload } from "@/api/hooks";
import type { User, UserRole } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ErrorState, PageHeader } from "@/components/ui/Card";
import { Field, Input, Select, Toggle } from "@/components/ui/Form";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { useToast } from "@/components/ui/Toast";
import { formatRelative } from "@/lib/format";

const ROLE_HELP: Record<UserRole, string> = {
  admin: "Full access, including user management",
  operator: "Manage devices, topology, alerts and rules",
  viewer: "Read-only access",
};

function UserModal({ user, onClose }: { user?: User; onClose: () => void }) {
  const save = useSaveUser();
  const { notify } = useToast();
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    email: user?.email ?? "",
    full_name: user?.full_name ?? "",
    role: user?.role ?? ("viewer" as UserRole),
    is_active: user?.is_active ?? true,
    password: "",
  });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const payload: UserPayload = {
      email: form.email,
      full_name: form.full_name,
      role: form.role,
      is_active: form.is_active,
    };
    if (form.password) payload.password = form.password;
    try {
      await save.mutateAsync({ id: user?.id, payload });
      notify("success", user ? "User updated" : "User created");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save user");
    }
  }

  return (
    <Modal
      open
      title={user ? `Edit ${user.email}` : "Add user"}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" form="user-form" variant="primary" loading={save.isPending}>
            Save
          </Button>
        </>
      }
    >
      <form id="user-form" onSubmit={submit} className="space-y-4">
        <Field label="Email">
          {(id) => (
            <Input
              id={id}
              type="email"
              required
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          )}
        </Field>
        <Field label="Full name">
          {(id) => (
            <Input
              id={id}
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />
          )}
        </Field>
        <Field label="Role" hint={ROLE_HELP[form.role]}>
          {(id) => (
            <Select
              id={id}
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}
            >
              <option value="viewer">Viewer</option>
              <option value="operator">Operator</option>
              <option value="admin">Administrator</option>
            </Select>
          )}
        </Field>
        <Field
          label={user ? "New password" : "Password"}
          hint={user ? "Leave blank to keep the current password" : "At least 8 characters"}
        >
          {(id) => (
            <Input
              id={id}
              type="password"
              autoComplete="new-password"
              required={!user}
              minLength={8}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          )}
        </Field>
        <Toggle
          checked={form.is_active}
          onChange={(v) => setForm({ ...form, is_active: v })}
          label="Active"
          description="Inactive users cannot sign in."
        />
        {error && (
          <p role="alert" className="text-sm text-critical-text">
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}

export function UsersPage() {
  const { user: me } = useAuth();
  const users = useUsers();
  const remove = useDeleteUser();
  const { notify } = useToast();
  const [editing, setEditing] = useState<User | "new" | null>(null);
  const [deleting, setDeleting] = useState<User | null>(null);

  return (
    <>
      <PageHeader
        title="Users"
        description="Accounts and role-based access."
        actions={
          <Button
            variant="primary"
            icon={<UserPlus className="size-4" />}
            onClick={() => setEditing("new")}
          >
            Add user
          </Button>
        }
      />
      {users.isError && <ErrorState error={users.error} onRetry={() => users.refetch()} />}
      <div className="card overflow-hidden">
        {!users.data ? (
          <div className="p-6">
            <Spinner />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b border-line bg-surface-2 text-left text-xs text-ink-2">
              <tr>
                <th className="px-4 py-2.5 font-medium">User</th>
                <th className="px-4 py-2.5 font-medium">Role</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Last sign-in</th>
                <th className="px-4 py-2.5">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {users.data.map((u) => (
                <tr key={u.id}>
                  <td className="px-4 py-2.5">
                    <p className="font-medium">
                      {u.full_name || u.email}
                      {u.id === me?.id && (
                        <span className="ml-1.5 text-xs text-ink-muted">(you)</span>
                      )}
                    </p>
                    <p className="text-xs text-ink-muted">{u.email}</p>
                  </td>
                  <td className="px-4 py-2.5 capitalize">{u.role}</td>
                  <td className="px-4 py-2.5">
                    {u.is_active ? (
                      <Badge>Active</Badge>
                    ) : (
                      <Badge className="text-ink-muted">Disabled</Badge>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-ink-muted">
                    {formatRelative(u.last_login_at)}
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex justify-end gap-0.5">
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`Edit ${u.email}`}
                        icon={<Pencil className="size-3.5" />}
                        onClick={() => setEditing(u)}
                      />
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`Delete ${u.email}`}
                        disabled={u.id === me?.id}
                        icon={<Trash2 className="size-3.5" />}
                        onClick={() => setDeleting(u)}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {editing && (
        <UserModal
          user={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)}
        />
      )}
      <ConfirmDialog
        open={!!deleting}
        title="Delete user"
        message={
          <>
            Delete the account <strong>{deleting?.email}</strong>?
          </>
        }
        loading={remove.isPending}
        onConfirm={() =>
          deleting &&
          remove.mutateAsync(deleting.id).then(
            () => {
              notify("success", "User deleted");
              setDeleting(null);
            },
            (err: Error) => notify("error", "Delete failed", err.message),
          )
        }
        onClose={() => setDeleting(null)}
      />
    </>
  );
}
