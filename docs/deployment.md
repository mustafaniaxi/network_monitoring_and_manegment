# Deployment

## Option 1 - Docker Compose (recommended)

Requirements: Docker Engine 24+ with the Compose plugin.

```bash
git clone https://github.com/mustafaniaxi/network_monitoring_and_manegment.git netmon
cd netmon
cp .env.example .env
```

Edit `.env` and set at least:

```bash
NETMON_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
POSTGRES_PASSWORD=<strong password>
NETMON_FIRST_ADMIN_EMAIL=you@example.com
NETMON_FIRST_ADMIN_PASSWORD=<temporary password>
```

Start the stack:

```bash
docker compose up -d --build
docker compose ps          # all services should become "healthy"
```

Open <http://localhost:8080> and sign in. Change the administrator password under
**Settings**, then add devices or run a **Discovery** scan.

What runs:

| Service | Image | Purpose |
|---|---|---|
| `db` | `postgres:16-alpine` | Persistent storage (named volume `pgdata`) |
| `backend` | `netmon-backend` | API + monitoring engine. Applies migrations on start. Runs as UID 1000. |
| `frontend` | `netmon-frontend` | nginx serving the UI and proxying `/api` (incl. WebSockets) to the backend |

### Demo mode

```bash
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
```

Starts with a simulated office network (router, switch, servers, AP, PCs, printer) and a week
of synthetic history. Nothing on your network is probed. The UI shows a *Simulated data* badge.

### Network access for monitoring

* **ICMP**: the backend container runs unprivileged and uses ICMP datagram sockets, enabled by
  the `net.ipv4.ping_group_range` sysctl in `docker-compose.yml`. No `NET_RAW` capability is
  needed.
* **Reaching devices**: the backend reaches anything routable from the Docker host through
  Docker's NAT. To monitor a network that is only reachable on a specific host interface, or to
  preserve source addresses for SNMP ACLs, run the backend with `network_mode: host` (and point
  `NETMON_API_UPSTREAM` of the frontend at the host).
* **SNMP**: allow UDP/161 from the NetMon host on your devices and configure a read-only
  community or (preferably) an SNMPv3 user with `authPriv`.

## TLS / reverse proxy

Terminate HTTPS in front of the `frontend` container. Example with Caddy (automatic
certificates):

```caddyfile
netmon.example.com {
    reverse_proxy localhost:8080
}
```

Example nginx server block:

```nginx
server {
    listen 443 ssl http2;
    server_name netmon.example.com;
    ssl_certificate     /etc/ssl/netmon.crt;
    ssl_certificate_key /etc/ssl/netmon.key;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade $http_upgrade;     # WebSocket live updates
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }
}
```

Set `NETMON_PUBLIC_URL=https://netmon.example.com` in `.env`.

## Option 2 - Manual installation (Linux VM)

```bash
# PostgreSQL
sudo apt install postgresql
sudo -u postgres createuser --pwprompt netmon
sudo -u postgres createdb -O netmon netmon

# Backend
curl -LsSf https://astral.sh/uv/install.sh | sh
cd backend
uv sync --no-dev
export NETMON_DATABASE_URL=postgresql+asyncpg://netmon:<password>@localhost/netmon
export NETMON_SECRET_KEY=<long random string>
export NETMON_ENVIRONMENT=production
uv run netmon init                      # migrations + first admin + default rules
uv run netmon serve --host 127.0.0.1 --port 8000

# Frontend
cd ../frontend
npm ci && npm run build                 # static files in frontend/dist
```

Serve `frontend/dist` with nginx using [`frontend/docker/nginx.conf.template`](../frontend/docker/nginx.conf.template)
(replace `${NETMON_API_UPSTREAM}` with `127.0.0.1:8000`). Run the backend under systemd:

```ini
# /etc/systemd/system/netmon.service
[Unit]
Description=NetMon API and monitoring engine
After=network-online.target postgresql.service

[Service]
User=netmon
WorkingDirectory=/opt/netmon/backend
EnvironmentFile=/etc/netmon.env
ExecStart=/opt/netmon/backend/.venv/bin/netmon serve --host 127.0.0.1 --port 8000
Restart=on-failure
# Unprivileged ICMP for the service user's group:
#   echo 'net.ipv4.ping_group_range = 0 2147483647' | sudo tee /etc/sysctl.d/90-ping.conf

[Install]
WantedBy=multi-user.target
```

## Operations

**Health checks**

* `GET /health/live` - process is up (used by the container healthcheck)
* `GET /health/ready` - database reachable and monitoring engine running (returns 503 otherwise)

**Metrics** - `GET /metrics` exposes Prometheus metrics (`netmon_device_up`,
`netmon_device_latency_ms`, `netmon_device_packet_loss_percent`, `netmon_device_cpu_percent`,
`netmon_device_throughput_bps`, `netmon_poll_duration_seconds`, `netmon_alerts_opened_total`,
...). Restrict it to your monitoring network at the proxy if needed.

**Logs** - JSON lines on stdout in the container (`docker compose logs -f backend`).

**Backups**

```bash
docker compose exec -T db pg_dump -U netmon -Fc netmon > netmon-$(date +%F).dump
# restore
docker compose exec -T db pg_restore -U netmon -d netmon --clean < netmon-2026-10-01.dump
```

**Upgrades**

```bash
git pull
docker compose up -d --build     # migrations run automatically on start
```

**Admin recovery** - reset or create an administrator from the CLI:

```bash
docker compose exec backend netmon create-admin -e you@example.com
```
