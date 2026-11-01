# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------- build stage
FROM python:3.15-slim AS builder
RUN pip install --no-cache-dir "uv>=0.8,<0.9"
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app

# Dependencies first so they are cached independently of source changes.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY netmon ./netmon
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# ---------------------------------------------------------------- runtime stage
FROM python:3.15-slim AS runtime
LABEL org.opencontainers.image.title="netmon-backend" \
      org.opencontainers.image.description="NetMon API and monitoring engine" \
      org.opencontainers.image.licenses="MIT"

# ICMP runs over unprivileged datagram sockets (see net.ipv4.ping_group_range in
# docker-compose.yml), so the image needs neither root nor CAP_NET_RAW.
RUN groupadd --system --gid 1000 netmon \
    && useradd --system --uid 1000 --gid netmon --home-dir /app --shell /usr/sbin/nologin netmon

WORKDIR /app
COPY --from=builder --chown=netmon:netmon /app /app
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NETMON_LOG_FORMAT=json

USER netmon
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=4)"

ENTRYPOINT ["entrypoint.sh"]
CMD ["netmon", "serve", "--host", "0.0.0.0", "--port", "8000"]
