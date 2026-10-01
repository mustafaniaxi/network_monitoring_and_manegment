#!/bin/sh
# Container entrypoint: apply migrations (and optionally seed demo data), then exec the CMD.
set -eu

if [ "${NETMON_SKIP_MIGRATIONS:-0}" != "1" ]; then
    echo "entrypoint: applying database migrations"
    netmon migrate
fi

if [ "${NETMON_SEED_DEMO:-0}" = "1" ]; then
    echo "entrypoint: seeding demo network"
    netmon seed-demo --history-hours "${NETMON_SEED_HISTORY_HOURS:-0}"
fi

exec "$@"
