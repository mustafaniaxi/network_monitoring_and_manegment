# NetMon backend

FastAPI service and asynchronous monitoring engine for the NetMon Network Monitoring and
Management System. See the [project README](../README.md) for the full documentation.

```bash
uv sync                                   # install runtime + dev dependencies
uv run netmon init --demo                 # migrate, create admin, seed demo network
NETMON_MONITOR_MODE=simulation uv run netmon serve --reload
uv run pytest                             # test suite
uv run ruff check . && uv run mypy netmon # lint + type-check
```

Interactive API documentation is served at <http://localhost:8000/docs>.
