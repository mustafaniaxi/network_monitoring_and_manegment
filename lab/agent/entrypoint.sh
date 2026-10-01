#!/bin/sh
# Render snmpd.conf from environment variables, start optional services, run snmpd in the foreground.
set -eu

: "${SNMP_COMMUNITY:=netmon-lab}"
: "${SYS_NAME:=$(hostname)}"
: "${SYS_LOCATION:=NetMon virtual lab}"
: "${SYS_DESCR:=Linux $(hostname) NetMon lab agent}"

mkdir -p /etc/snmp /var/lib/net-snmp
cat > /etc/snmp/snmpd.conf <<CONF
agentaddress udp:161
rocommunity ${SNMP_COMMUNITY} default
sysName ${SYS_NAME}
sysLocation ${SYS_LOCATION}
sysDescr ${SYS_DESCR}
sysContact lab@netmon.local
CONF

if [ -n "${SNMPV3_USER:-}" ]; then
    echo "createUser ${SNMPV3_USER} SHA \"${SNMPV3_AUTH_KEY}\" AES \"${SNMPV3_PRIV_KEY}\"" >> /etc/snmp/snmpd.conf
    echo "rouser ${SNMPV3_USER} priv" >> /etc/snmp/snmpd.conf
fi

# Optional TCP service (e.g. 80 for a "web server", 5432 for a "database") for TCP checks.
if [ -n "${SERVICE_PORT:-}" ]; then
    mkdir -p /www
    head -c 5000000 /dev/urandom > /www/payload.bin
    echo "NetMon lab service on ${SYS_NAME}" > /www/index.html
    httpd -p "${SERVICE_PORT}" -h /www
fi

# Optional traffic generator: download from TRAFFIC_TARGET in a loop to create interface load.
if [ -n "${TRAFFIC_TARGET:-}" ]; then
    (while true; do wget -q -O /dev/null "${TRAFFIC_TARGET}" || true; sleep "${TRAFFIC_PAUSE:-1}"; done) &
fi

exec snmpd -f -Lo -C -c /etc/snmp/snmpd.conf
