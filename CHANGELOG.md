# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-01

### Added
- Asynchronous monitoring engine: ICMP and TCP availability probes (latency, jitter, packet
  loss) and an SNMP v1/v2c/v3 collector (CPU, memory, interface status, 32/64-bit traffic
  counters with wrap handling and bandwidth utilisation).
- Device management with write-only SNMP credentials, tags, per-device poll intervals.
- Network discovery: background subnet sweeps with SNMP fingerprinting and bulk import.
- Alert engine: scoped threshold rules (device > type > global), debouncing, de-duplication,
  auto-resolution, acknowledgement, webhook (Slack/Mattermost/Discord) and e-mail delivery.
- Topology map with automatic hierarchical layout, saved positions and link editing.
- Historical analytics: time-bucketed series, availability/MTTR report, frequently failing
  devices, traffic heatmap, bottlenecks and degradation detection, CSV exports.
- Research tooling: detection-delay statistics, monitoring-overhead accounting, experiment
  scripts and a containerised virtual lab with SNMP agents.
- React dashboard with live WebSocket updates, light/dark themes and accessible charts.
- JWT authentication, Argon2 password hashing, role-based access control, login throttling.
- Docker images, Compose stacks (production, demo, lab), CI and release workflows.
