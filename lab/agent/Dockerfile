# Lightweight lab "device": a net-snmp agent (SNMPv2c + SNMPv3) with an optional TCP service.
FROM alpine:3.24
RUN apk add --no-cache net-snmp busybox-extras
COPY --chmod=755 entrypoint.sh /usr/local/bin/entrypoint.sh
EXPOSE 161/udp
ENTRYPOINT ["entrypoint.sh"]
