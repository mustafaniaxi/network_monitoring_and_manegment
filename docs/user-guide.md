# User guide

A tour of the web interface. Every page updates live while the WebSocket indicator in the top
bar shows **Live**; otherwise data refreshes every 30 seconds.

## Roles

* **Viewer** - read-only access to everything except user management.
* **Operator** - additionally manages devices, discovery, topology, alerts and alert rules.
* **Administrator** - additionally manages user accounts.

## Dashboard

![Dashboard](images/dashboard-dark.png)

* **Stat tiles** - devices online, 24 h availability, average latency and packet loss over the
  last hour, current total throughput, open alerts by severity.
* **Charts** - network-wide average latency, availability, total traffic (in/out) and packet
  loss for the range chosen at the top right (1 h - 30 d). The icon at the top of each chart
  switches to a **table view** with the same numbers.
* **Device status** - problem devices first. **Open alerts** - the newest alerts.
  **Inventory by type** - device counts.

## Devices

Search by name, address, location or vendor; filter by status and type. Operators can:

* **Add device** - name, IP address or hostname, type, location, tags.
  * *Availability check*: ICMP ping (default) or TCP connect to a port, for hosts that block ping.
  * *Poll interval*: leave blank for the global default.
  * *SNMP*: v1/v2c community or SNMPv3 user (auth SHA/MD5/SHA-256/SHA-512, privacy
    AES-128/AES-256/DES). Secrets are never shown again; leave the field blank to keep them.
* **Check now** (↻) - poll immediately.
* **Edit / Delete**. Turning monitoring off keeps the device in the inventory, sets its status
  to *Unknown* and resolves its open alerts.

### Device detail

![Device detail](images/device-detail-dark.png)

Current latency, loss, CPU, memory, traffic and uptime; history charts for latency
(average and maximum), availability, packet loss, CPU & memory and traffic; the SNMP interface
table with status, speed, rates and utilisation; system details and recent alerts. **Export**
downloads the raw measurements for the selected range as CSV.

## Topology

![Topology](images/topology-dark.png)

Devices are arranged automatically from the upstream internet/router down to end devices.
Status is shown by the coloured bar and label on each node and by the link colour (a link
turns red when either end is offline). Operators can:

* drag devices to arrange the map (positions are saved);
* drag from a device's bottom handle to another device to **create a link**;
* click a link and **Remove link**;
* **Auto layout** to discard manual positions.

## Alerts

Open alerts can be **acknowledged** (someone is working on it) or **resolved** manually; they
also resolve automatically as soon as the condition clears. Durations are measured from the
first failing measurement.

**Rules** tab - six rules are created on first start (unreachable, packet loss > 20 %, latency
> 200 ms, CPU > 90 %, memory > 90 %, bandwidth > 80 %). Each rule has a condition, a number of
consecutive breaches (to ignore one-off spikes), a severity and a scope (all devices, a device
type, or one device). A more specific rule overrides a more general one for the same metric.

Notifications (webhook / e-mail) are configured by the administrator through environment
variables - see [configuration.md](configuration.md#notifications).

## Discovery

Enter a subnet in CIDR notation (up to 1024 addresses by default), choose ICMP or TCP probing
and optionally an SNMP community for fingerprinting. Responding hosts appear with round-trip
time, reverse-DNS name, SNMP system description and a suggested device type. Adjust names and
types, select hosts and **Add devices** - monitoring starts immediately. Already registered
addresses are marked and skipped.

## Reports

![Reports](images/reports-dark.png)

For the selected range:

* **Availability by device** - availability, average/maximum latency, jitter, loss, number of
  outages, total downtime and mean time to recover (sortable; CSV export).
* **Most frequently failing** devices.
* **High-traffic periods** - average throughput by weekday and hour (your local time).
* **Potential bottlenecks** - devices ranked by link utilisation, CPU and loss; busiest
  interfaces.
* **Performance degradation** - first half vs second half of the range; devices whose latency,
  loss or availability got significantly worse are flagged.
* Tiles at the top summarise network availability, outages, downtime, mean time to detect and
  mean time to recover.

## Settings

Change your name and password, see the system configuration, and watch the **monitoring
overhead** panel (polls per minute, packets and SNMP requests sent, estimated monitoring
traffic, server CPU and memory) - useful for the research evaluation.

## Users (administrators)

Create accounts, assign roles, deactivate users or reset their passwords. The last active
administrator cannot be removed or demoted.
