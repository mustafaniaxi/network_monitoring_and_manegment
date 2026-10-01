import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Form";

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? "/";
  if (user) return <Navigate to={from} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-full place-items-center bg-page px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <svg viewBox="0 0 32 32" className="size-11" aria-hidden>
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
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Sign in to NetMon</h1>
            <p className="mt-1 text-sm text-ink-2">Network Monitoring and Management System</p>
          </div>
        </div>
        <form onSubmit={submit} className="card space-y-4 p-6" noValidate>
          <Field label="Email">
            {(id) => (
              <Input
                id={id}
                type="email"
                autoComplete="username"
                autoFocus
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            )}
          </Field>
          <Field label="Password">
            {(id) => (
              <Input
                id={id}
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            )}
          </Field>
          {error && (
            <p role="alert" className="text-sm text-critical-text">
              {error}
            </p>
          )}
          <Button
            type="submit"
            variant="primary"
            className="w-full"
            loading={busy}
            disabled={!email || !password}
          >
            Sign in
          </Button>
        </form>
        <p className="mt-6 text-center text-xs text-ink-muted">
          First run? The initial administrator is configured with NETMON_FIRST_ADMIN_EMAIL /
          NETMON_FIRST_ADMIN_PASSWORD.
        </p>
      </div>
    </div>
  );
}
