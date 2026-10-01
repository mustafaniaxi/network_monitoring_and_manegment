# Development guide

## Prerequisites

* Python 3.11+ and [uv](https://docs.astral.sh/uv/)
* Node.js 22+
* Optional: Docker (stack, lab), PostgreSQL 16 (to test against Postgres locally),
  `snmpd` (net-snmp) for the SNMP integration tests

## Getting started

```bash
make install          # uv sync + npm ci
make dev-db           # SQLite DB in backend/netmon.db with demo devices and 7 days of history
make dev-backend      # http://localhost:8000 (docs at /docs), simulation mode, auto-reload
make dev-frontend     # http://localhost:5173, proxies /api and WebSockets to :8000
```

Sign in with `admin@netmon.local` / `ChangeMe123!`.

To monitor your real network during development, run the backend in live mode:
`cd backend && uv run netmon serve --reload` (ICMP needs root, `CAP_NET_RAW`, or
`sysctl net.ipv4.ping_group_range="0 2147483647"`).

## Repository layout

```
backend/            FastAPI service + monitoring engine (Python package `netmon`)
  netmon/           application code (see docs/architecture.md)
  tests/            pytest suite (SQLite by default, PostgreSQL via NETMON_TEST_DATABASE_URL)
frontend/           React + TypeScript SPA (Vite)
  src/api/          typed API client, React Query hooks, shared types
  src/components/   UI kit, charts, layout
  src/pages/        one component per route
lab/                Docker virtual lab (SNMP agent image, compose overlay, setup script)
research/           experiment scripts and API client for the evaluation chapter
docs/               documentation
```

## Backend

```bash
cd backend
uv run pytest                         # 90+ tests
uv run pytest -k alert -x             # subset, stop on first failure
uv run pytest --cov                   # coverage report
uv run ruff check . && uv run ruff format .
uv run mypy netmon                    # strict mode
```

Against PostgreSQL:

```bash
NETMON_TEST_DATABASE_URL=postgresql+asyncpg://netmon:netmon@localhost/netmon_test uv run pytest
```

**Testing approach.** Tests drive the real application through `httpx.ASGITransport` with a
`FakeBackend` that scripts what each host "answers" (`tests/conftest.py`), so the full poll →
persist → alert → event pipeline is exercised deterministically without a network.
`tests/test_snmp_integration.py` starts a real `snmpd` on a random port and polls it over
SNMPv1, v2c and v3 (skipped when `snmpd` is not installed).

**Migrations.** After changing models:

```bash
make migration m="add device serial number"   # autogenerate
# review netmon/db/migrations/versions/<new file>.py, then
uv run netmon migrate
uv run alembic check                           # must report no differences
```

Keep column types portable (string-backed enums via `str_enum`, `UTCDateTime`, `Counter`).

**Adding a metric** (example: temperature):

1. Collect it in `services/monitoring/snmp.py` (`SnmpSnapshot`) and the simulation backend.
2. Add a column to `MetricSample` (+ `last_*` on `Device` if shown live) and a migration.
3. Store it in `MonitoringService._apply_snmp`.
4. Add it to `AlertMetric` to make it alertable, and to `analytics.device_series`.
5. Expose it in `schemas/` and the frontend types, then chart it.

## Frontend

```bash
cd frontend
npm run dev
npm test            # Vitest + Testing Library
npm run lint        # ESLint (incl. React hooks/compiler rules)
npm run typecheck
npm run build
```

Conventions:

* All server state goes through hooks in `src/api/hooks.ts` (one place for endpoints and
  cache keys); components never call `fetch` directly.
* Design tokens live in `src/index.css` (CSS variables, light and dark). Use the Tailwind
  theme names (`bg-surface`, `text-ink-2`, `border-line`, ...) rather than raw colours.

### Charts

The charts follow a small set of data-visualisation rules:

* one y-axis per chart - never dual axes; different units get separate charts;
* categorical colours in fixed order (`--series-1` blue, `--series-2` orange, ...), so a
  series keeps its colour everywhere;
* status colours (`good`, `warning`, `critical`) are reserved for state and always paired with
  an icon and a text label;
* 2 px lines, solid hairline grid, crosshair tooltip that lists every series;
* a legend whenever there are two or more series;
* every chart has a table-view twin (`ChartCard`), and refetches keep the previous render
  dimmed instead of flashing a loader;
* sequential (single-hue) ramp for magnitude in the heatmap, with its own dark-mode steps.

## Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request:

1. **Backend** (Python 3.11 and 3.12): ruff, ruff format, mypy, pytest on SQLite with
   coverage, pytest on PostgreSQL 16, SNMP integration tests, migration up/check/down.
2. **Frontend**: ESLint, Prettier, TypeScript, Vitest, production build.
3. **Scripts**: lint/compile the lab and research scripts.
4. **Docker**: build all images, validate the compose files, start the demo stack and smoke
   test login and the dashboard through the nginx container.

Tagging `vX.Y.Z` runs `.github/workflows/release.yml`, which publishes multi-arch images to
GitHub Container Registry.
