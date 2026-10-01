# Contributing to NetMon

Thanks for your interest in improving NetMon! This guide explains how to get a development
environment running and what we expect from changes.

## Development setup

Prerequisites: **Python 3.11+** with [uv](https://docs.astral.sh/uv/), **Node.js 22+**, and
optionally Docker.

```bash
make install        # backend (uv sync) + frontend (npm ci)
make dev-db         # SQLite database with the demo network and a week of history
make dev-backend    # API on http://localhost:8000 (simulation mode, auto-reload)
make dev-frontend   # UI on http://localhost:5173 (proxies /api to the backend)
```

Sign in with `admin@netmon.local` / `ChangeMe123!` (development defaults) and change the password.

See [docs/development.md](docs/development.md) for the project layout and architecture notes.

## Making changes

1. Create a branch from `main` (`feature/…`, `fix/…`, `docs/…`).
2. Keep changes focused; one logical change per pull request.
3. Add or update tests. Backend code is held to `mypy --strict`; keep it that way.
4. If you change ORM models, add a migration: `make migration m="add xyz"` and review it.
5. Update documentation when behaviour, configuration or the API changes.
6. Run `make lint test` before pushing. CI runs the same checks plus PostgreSQL tests,
   an SNMP integration test and a Docker smoke test.

## Commit messages

Use the imperative mood and explain *why* in the body when it is not obvious:

```
Add SNMPv3 AES-256 privacy support

Some lab switches only accept AES-256; expose it in the device form and map it
to pysnmp's usmAesCfb256Protocol.
```

## Code style

- **Python**: `ruff` (lint + format), type hints everywhere, async I/O only in request paths.
- **TypeScript**: ESLint + Prettier, no `any`, server state through TanStack Query hooks in
  `src/api/hooks.ts`.
- **UI**: status colours are reserved for state and always paired with an icon and label;
  charts follow the rules in [docs/development.md](docs/development.md#charts).

## Reporting issues

Use the GitHub issue templates. For security problems, follow [SECURITY.md](SECURITY.md)
instead of opening a public issue.
