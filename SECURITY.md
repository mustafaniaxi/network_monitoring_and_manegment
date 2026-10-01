# Security policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Report them privately through
[GitHub security advisories](https://github.com/mustafaniaxi/network_monitoring_and_manegment/security/advisories/new).
Include steps to reproduce and the affected version. You should receive a response within a
few days.

## Supported versions

Security fixes are applied to the latest release.

## Security model and hardening

NetMon is designed to run inside a trusted management network.

- **Authentication**: JWT bearer tokens signed with `NETMON_SECRET_KEY` (HS256). The
  application refuses to start in `production` with the default or a short key. Tokens are
  bound to a fingerprint of the password hash, so changing a password revokes old sessions.
- **Passwords**: Argon2id hashing; failed logins are throttled per client and account.
- **Authorisation**: three roles (`admin`, `operator`, `viewer`), enforced on every endpoint.
- **SNMP credentials** are write-only through the API (never returned to clients) but are
  stored in the database in plain text because the poller needs them. Protect database access
  and backups accordingly, and prefer SNMPv3 with authentication and privacy (`authPriv`).
- **Transport**: terminate TLS in front of the web container (reverse proxy or load
  balancer); see [docs/deployment.md](docs/deployment.md).
- **Containers** run as an unprivileged user; ICMP uses unprivileged datagram sockets, so no
  `NET_RAW` capability is required.
- **Discovery** scans are limited in size (`NETMON_DISCOVERY_MAX_HOSTS`) and restricted to
  operators and administrators. Only scan networks you are authorised to scan.
