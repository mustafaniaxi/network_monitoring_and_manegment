import { Link } from "react-router";

export function NotFoundPage() {
  return (
    <div className="grid place-items-center py-24 text-center">
      <p className="text-5xl font-semibold text-ink-muted">404</p>
      <p className="mt-2 text-sm text-ink-2">This page does not exist.</p>
      <Link to="/" className="mt-4 text-sm font-medium text-accent hover:underline">
        Back to the dashboard
      </Link>
    </div>
  );
}
