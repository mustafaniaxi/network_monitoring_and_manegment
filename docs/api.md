# API guide

The REST API is served under `/api/v1`. Interactive documentation (Swagger UI) is available at
`/docs`, ReDoc at `/redoc`, and the OpenAPI schema at `/api/v1/openapi.json`.

## Authentication

```bash
curl -s -X POST http://localhost:8080/api/v1/auth/login \
     -d "username=admin@example.com&password=secret" | jq .
```

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 43200,
  "user": { "id": 1, "email": "admin@example.com", "role": "admin", "...": "..." }
}
```

Send the token on every request: `Authorization: Bearer <token>`. Tokens expire after
`NETMON_ACCESS_TOKEN_EXPIRE_MINUTES` and are revoked when the user's password changes.
Repeated failed logins return `429 Too Many Requests` with a `Retry-After` header.

### Roles

| Role | Read | Devices, topology, discovery, alerts, rules | Users |
|---|---|---|---|
| `viewer` | ✔ | | |
| `operator` | ✔ | ✔ | |
| `admin` | ✔ | ✔ | ✔ |

## Endpoints

| Area | Method & path | Purpose |
|---|---|---|
| Auth | `POST /auth/login` | OAuth2 password flow (form fields `username`, `password`) |
| | `GET /auth/me`, `PATCH /auth/me` | Current user / update display name |
| | `POST /auth/change-password` | Change own password |
| Users | `GET/POST /users`, `PATCH/DELETE /users/{id}` | User administration (admin) |
| Devices | `GET /devices?search=&status=&device_type=&sort=&page=&page_size=` | Paginated inventory |
| | `POST /devices`, `GET/PATCH/DELETE /devices/{id}` | CRUD (SNMP secrets are write-only) |
| | `POST /devices/{id}/check` | Poll immediately |
| | `GET /devices/{id}/metrics?range=1h\|6h\|24h\|7d\|30d` | Time-bucketed history |
| | `GET /devices/{id}/interfaces`, `GET /devices/{id}/alerts` | Interface table, alert history |
| Discovery | `POST /discovery/scans` | Start a sweep `{cidr, method, tcp_port?, snmp_community?}` → job |
| | `GET /discovery/scans`, `GET/DELETE /discovery/scans/{id}` | Progress/results, cancel |
| | `POST /discovery/import` | Register discovered hosts |
| Topology | `GET /topology` | Nodes (devices) and edges (links) with live status |
| | `POST /topology/links`, `PATCH/DELETE /topology/links/{id}` | Manage links |
| | `PUT /topology/positions`, `DELETE /topology/positions` | Save / reset map layout |
| Alerts | `GET /alerts?status=&severity=&device_id=&open_only=` | Paginated alerts |
| | `GET /alerts/summary` | Open counts by state and severity |
| | `POST /alerts/{id}/acknowledge`, `POST /alerts/{id}/resolve` | Lifecycle actions |
| Rules | `GET/POST /alert-rules`, `PATCH/DELETE /alert-rules/{id}` | Threshold rules |
| Dashboard | `GET /dashboard/summary`, `GET /dashboard/timeseries?range=` | KPIs and network-wide series |
| Reports | `GET /reports/availability`, `GET /reports/availability.csv` | Uptime, latency, outages, MTTR |
| | `GET /reports/top-failing`, `/reports/traffic-heatmap`, `/reports/bottlenecks`, `/reports/degradation` | Historical analysis |
| | `GET /reports/detection` | Detection-delay and recovery statistics (research) |
| | `GET /reports/samples.csv?range=&device_id=` | Raw measurements export |
| System | `GET /system/info`, `GET /system/stats` | Configuration and monitoring overhead |
| Live | `WS /ws?token=<jwt>` | Event stream |
| Health | `GET /health/live`, `GET /health/ready`, `GET /metrics` | Probes and Prometheus (no `/api/v1` prefix) |

Errors use FastAPI's format: `{"detail": "message"}` or, for validation errors (422), a list
of `{loc, msg, type}` objects.

## Examples

Register a server checked over TCP/443 with SNMPv3:

```bash
curl -s -X POST http://localhost:8080/api/v1/devices \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
        "name": "Web Server", "ip_address": "192.168.1.10", "device_type": "server",
        "check_method": "tcp", "tcp_port": 443,
        "snmp_enabled": true, "snmp_version": "v3", "snmp_v3_username": "netmon",
        "snmp_v3_auth_protocol": "sha", "snmp_v3_auth_key": "auth-secret",
        "snmp_v3_priv_protocol": "aes128", "snmp_v3_priv_key": "priv-secret"
      }'
```

Raise the latency threshold for all access points:

```bash
curl -s -X POST http://localhost:8080/api/v1/alert-rules \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Wi-Fi latency", "metric": "latency_ms", "operator": "gt",
       "threshold": 400, "consecutive": 3, "severity": "warning",
       "device_type": "access_point"}'
```

Export a week of raw measurements:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/reports/samples.csv?range=7d" -o samples-7d.csv
```

## WebSocket events

```js
const ws = new WebSocket(`wss://netmon.example.com/api/v1/ws?token=${token}`);
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

```json
{"type": "device.status", "ts": "2026-10-01T17:12:03Z",
 "data": {"device_id": 6, "name": "Database Server", "status": "down", "previous": "up"}}
{"type": "alert.opened", "ts": "2026-10-01T17:12:03Z",
 "data": {"id": 42, "device_id": 6, "device": "Database Server", "severity": "critical",
          "title": "Device unreachable", "message": "ALERT: Database Server is unreachable."}}
```

Event types: `hello`, `ping` (keep-alive every 25 s), `device.sample`, `device.status`,
`alert.opened`, `alert.resolved`. The connection is closed with code 1008 if the token is
invalid.
