# Configuration reference

The backend is configured entirely through environment variables prefixed with `NETMON_`
(or a `.env` file in the working directory). Values are validated at start-up; an invalid
value stops the process with a clear error. Lists accept comma-separated values.

## Application

| Variable | Default | Description |
|---|---|---|
| `NETMON_ENVIRONMENT` | `development` | `development`, `production` or `test`. In `production` the server refuses to start with the default or a short secret key. |
| `NETMON_APP_NAME` | `NetMon` | Name shown in the API title and system info. |
| `NETMON_API_PREFIX` | `/api/v1` | Mount point of the REST API. |
| `NETMON_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `NETMON_LOG_FORMAT` | `console` | `console` (human readable) or `json` (one JSON object per line; default in the Docker image). |
| `NETMON_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Browser origins allowed to call the API directly. Not needed when the UI is served through the bundled nginx (same origin). |
| `NETMON_PROMETHEUS_ENABLED` | `true` | Expose Prometheus metrics at `/metrics`. |

## Database

| Variable | Default | Description |
|---|---|---|
| `NETMON_DATABASE_URL` | `sqlite+aiosqlite:///./netmon.db` | SQLAlchemy async URL. Use `postgresql+asyncpg://user:pass@host:5432/db` in production. |
| `NETMON_DB_POOL_SIZE` | `10` | Connection pool size (PostgreSQL). |
| `NETMON_DB_ECHO` | `false` | Log every SQL statement (debugging only). |
| `NETMON_DB_AUTO_CREATE` | `false` | Create tables at start-up without migrations. For tests and throw-away databases only - use `netmon migrate` otherwise. |

## Security

| Variable | Default | Description |
|---|---|---|
| `NETMON_SECRET_KEY` | *insecure development value* | Key used to sign JWTs. **Required in production** (at least 32 characters). Changing it signs everyone out. |
| `NETMON_JWT_ALGORITHM` | `HS256` | JWT signing algorithm. |
| `NETMON_ACCESS_TOKEN_EXPIRE_MINUTES` | `720` | Session lifetime (12 hours). |
| `NETMON_LOGIN_MAX_ATTEMPTS` | `5` | Failed logins allowed per client + account within the lockout window. |
| `NETMON_LOGIN_LOCKOUT_SECONDS` | `300` | Lockout window length. |
| `NETMON_FIRST_ADMIN_EMAIL` | `admin@netmon.local` | Administrator created automatically when the user table is empty. |
| `NETMON_FIRST_ADMIN_PASSWORD` | `ChangeMe123!` | Its initial password - change it immediately after the first sign-in. |

## Monitoring engine

| Variable | Default | Description |
|---|---|---|
| `NETMON_MONITORING_ENABLED` | `true` | Run the polling scheduler. Disable to run an API-only replica. |
| `NETMON_MONITOR_MODE` | `live` | `live` probes the real network; `simulation` produces realistic synthetic measurements (demos, UI work, load tests). |
| `NETMON_POLL_INTERVAL_SECONDS` | `30` | Default poll interval (5-3600). Devices can override it. |
| `NETMON_MAX_CONCURRENT_POLLS` | `64` | Upper bound on simultaneous device polls. |
| `NETMON_DOWN_AFTER_FAILURES` | `2` | Consecutive failed probes before a device is marked *down* (flap protection). |
| `NETMON_DEGRADED_LATENCY_MS` | `150` | Average RTT at or above which a reachable device is *degraded*. |
| `NETMON_DEGRADED_PACKET_LOSS` | `10` | Packet loss (%) at or above which a reachable device is *degraded*. |
| `NETMON_ICMP_COUNT` | `3` | Echo requests per poll. |
| `NETMON_ICMP_INTERVAL` | `0.2` | Seconds between echo requests. |
| `NETMON_ICMP_TIMEOUT` | `1.0` | Seconds to wait for each reply. |
| `NETMON_ICMP_PRIVILEGED` | *auto* | `true` = raw sockets (root/`CAP_NET_RAW`), `false` = unprivileged datagram sockets (needs `net.ipv4.ping_group_range`). Auto-detected when unset; falls back to the `ping` binary if neither is allowed. |
| `NETMON_TCP_TIMEOUT` | `2.0` | TCP connect timeout for TCP-checked devices. |
| `NETMON_SNMP_TIMEOUT` | `2.0` | SNMP request timeout. |
| `NETMON_SNMP_RETRIES` | `1` | SNMP retries per request. |
| `NETMON_METRICS_RETENTION_DAYS` | `90` | Raw samples and resolved alerts older than this are deleted hourly. |
| `NETMON_SIMULATION_SEED` | *random* | Fixed seed for reproducible simulation runs. |

## Discovery

| Variable | Default | Description |
|---|---|---|
| `NETMON_DISCOVERY_MAX_HOSTS` | `1024` | Largest subnet a single scan may cover (a /22). |
| `NETMON_DISCOVERY_CONCURRENCY` | `128` | Parallel probes during a scan. |
| `NETMON_DISCOVERY_TIMEOUT` | `1.0` | Per-host probe timeout during a scan. |

## Notifications

Notifications are sent when an alert opens and when it resolves, for alerts at or above the
minimum severity. Delivery is asynchronous and never delays monitoring.

| Variable | Default | Description |
|---|---|---|
| `NETMON_ALERT_MIN_SEVERITY` | `warning` | `info`, `warning` or `critical`. |
| `NETMON_ALERT_WEBHOOK_URL` | - | Incoming-webhook URL. The JSON body carries `text` (Slack, Mattermost, Rocket.Chat), `content` (Discord) and a structured `alert` object for custom receivers. |
| `NETMON_SMTP_HOST` | - | SMTP server; e-mail is enabled when this and `NETMON_SMTP_TO` are set. |
| `NETMON_SMTP_PORT` | `587` | SMTP port. |
| `NETMON_SMTP_STARTTLS` | `true` | Upgrade the connection with STARTTLS. |
| `NETMON_SMTP_USERNAME` / `NETMON_SMTP_PASSWORD` | - | SMTP credentials (optional). |
| `NETMON_SMTP_FROM` | `netmon@localhost` | Sender address. |
| `NETMON_SMTP_TO` | - | Comma-separated recipients. |

## Container-only variables

| Variable | Where | Description |
|---|---|---|
| `NETMON_SKIP_MIGRATIONS` | backend image | `1` skips `netmon migrate` in the entrypoint (e.g. when migrations run as a separate job). |
| `NETMON_SEED_DEMO` | backend image | `1` inserts the demo network on start-up (only if no devices exist). |
| `NETMON_SEED_HISTORY_HOURS` | backend image | With `NETMON_SEED_DEMO=1`, back-fill this many hours of synthetic history. |
| `NETMON_API_UPSTREAM` | frontend image | `host:port` of the backend for the nginx reverse proxy (default `backend:8000`). |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | compose | Database created by the `db` service. |
| `NETMON_HTTP_PORT` | compose | Host port of the web UI (default `8080`). |
| `NETMON_PUBLIC_URL` | compose | Public URL of the UI (used as the CORS origin). |
