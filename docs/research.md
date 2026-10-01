# Research methodology

This document supports the monograph *"Design and Implementation of a Network Monitoring and
Management System"*. It defines the research question, the metrics, how NetMon measures them,
and step-by-step experiment procedures that produce CSV data for the evaluation chapter.

## Research question

> How effectively can a centralized network monitoring system detect device failures and
> network performance degradation in a small-scale network?

Sub-questions:

1. **Detection time** - how long after a failure does the operator see an alert?
2. **Detection accuracy** - are all injected failures detected, and are there false alarms?
3. **Monitoring overhead** - what does monitoring cost in network traffic, CPU and memory?
4. **Degradation detection** - are gradual performance problems (rising latency, packet
   loss, saturated links) surfaced?
5. **Configuration trade-offs** - how do poll interval and debouncing affect 1-3?

## Metrics and where they come from

| Metric | Definition | Source in NetMon |
|---|---|---|
| Detection time | failure injected → `device_down` alert visible via the API | `research/measure_detection.py` (end-to-end, wall clock) |
| Debounce delay | first failed probe → alert (`triggered_at - first_breach_at`) | `GET /api/v1/reports/detection`, alerts table |
| Status-change time | failure injected → device status `down` | `measure_detection.py` |
| Recovery detection time | failure removed → alert auto-resolved | `measure_detection.py` |
| Time to recover (MTTR) | first failed probe → resolution | `GET /api/v1/reports/availability`, Reports page |
| Detection rate | detected / injected failures | `measure_detection.py` summary |
| False positives | alerts opened with no injected failure | alerts list filtered to the experiment window |
| Monitoring traffic | probe packets + SNMP PDUs × estimated wire size | `GET /api/v1/system/stats`, `measure_overhead.py` |
| Server CPU / memory | NetMon process CPU % and RSS | `GET /api/v1/system/stats`, `measure_overhead.py` |
| Poll duration | time to probe + collect SNMP for one device | `metric_samples.poll_duration_ms`, Prometheus histogram |
| Availability | share of successful probes per device/period | Reports page, `availability.csv` |
| Degradation | latency/loss/availability change, first vs second half of a period | `GET /api/v1/reports/degradation` |

### Expected detection time (analytical model)

With poll interval *T*, *k* consecutive failures required (the `consecutive` setting of the
*Device unreachable* rule for alerts, `NETMON_DOWN_AFTER_FAILURES` for the device status - keep
them equal) and probe timeout *τ*, a failure at a uniformly random moment is first observed
after `U(0, T)`; *k − 1* further polls are needed and each failed probe takes up to *τ*:

```
E[detection] ≈ T/2 + (k − 1)·T + τ         range: [(k − 1)·T + τ,  k·T + τ]
```

For the defaults (*T* = 30 s, *k* = 2, *τ* ≈ 1 s): ≈ 46 s, between 31 s and 61 s.
For the lab settings (*T* = 10 s): ≈ 16 s. Comparing measured values with this model is a
good validation step for the evaluation chapter.

*Reference run (TCP-checked service, T = 5 s, k = 2, 3 trials, development machine):* detection
7.6-9.0 s (mean 8.6 s, model range 5-10 s), recovery detection ≈ 5.0 s, 3/3 detected.

## Experiment 1 - detection time and accuracy

Setup: Docker virtual lab ([virtual-lab.md](virtual-lab.md)), devices registered with
`lab/setup_lab.py --poll-interval 10`.

```bash
python3 research/measure_detection.py \
    --password '<admin password>' \
    --device "Lab DB Server" --container netmon-lab-db-1 \
    --trials 30 --cooldown 20 \
    --out research/results/detection-T10-k2.csv
```

The script waits until the device is healthy, injects a failure (`docker network
disconnect` by default, or `--method stop`, or any `--fail-cmd/--restore-cmd` such as
`VBoxManage controlvm VM2 setlinkstate1 off`), measures detection and recovery times, repeats,
and prints mean / median / standard deviation / p95.

Recommended matrix (change the interval with `setup_lab.py --poll-interval`; change *k* by
editing the *Device unreachable* rule on **Alerts → Rules** and setting
`NETMON_DOWN_AFTER_FAILURES` to the same value):

| Run | Poll interval *T* | *k* | Trials |
|---|---|---|---|
| A | 10 s | 1 | 30 |
| B | 10 s | 2 | 30 |
| C | 10 s | 3 | 30 |
| D | 30 s | 2 | 30 |
| E | 60 s | 2 | 30 |

Expected finding: detection time grows linearly with *T* and *k*; *k* = 1 is fastest but
produces false alarms on transient loss (see Experiment 3).

## Experiment 2 - monitoring overhead

Run NetMon in simulation mode so that device count can be scaled without hardware:

```bash
NETMON_MONITOR_MODE=simulation docker compose up -d
for n in 10 50 100 250 500; do
  python3 research/measure_overhead.py --password '<admin password>' \
      --add-devices $n --cleanup --duration 300 \
      --out research/results/overhead-$n.csv
done
```

Repeat in live mode against the lab for real network numbers. Report polls/min, packets/s,
estimated monitoring bandwidth, mean/max process CPU and peak memory per device count. The
estimate assumes 84-byte ICMP echo packets each way and ~600 bytes per SNMP exchange; it can
be validated with `tcpdump -i <lab bridge> -w overhead.pcap` and Wireshark's *Statistics →
Conversations*.

## Experiment 3 - false positives under packet loss

Inject random loss on a lab device and count alerts that should not fire:

```bash
docker run --rm --net container:netmon-lab-web-1 --cap-add NET_ADMIN nicolaka/netshoot \
    tc qdisc add dev eth0 root netem loss 20%
# run for 30 minutes with k = 1, then k = 2, then k = 3; compare the alert counts
docker run --rm --net container:netmon-lab-web-1 --cap-add NET_ADMIN nicolaka/netshoot \
    tc qdisc del dev eth0 root
```

With `netem delay 250ms` instead of `loss`, the same procedure evaluates latency alerts and
the degraded status.

## Experiment 4 - degradation and bottleneck detection

1. Let the lab run for at least a few hours (the traffic generator creates load).
2. Increase latency on one device half-way through: `tc qdisc add dev eth0 root netem delay 40ms`.
3. On the **Reports** page (range 6h or 24h) check that the device is flagged *Degrading* and
   appears in *Potential bottlenecks*; export `availability.csv` and `samples.csv`.

## Analysing the data

All CSV files have a header row and ISO-8601 timestamps. Example with pandas:

```python
import pandas as pd
runs = {name: pd.read_csv(f"research/results/detection-{name}.csv") for name in ["T10-k1", "T10-k2", "T10-k3"]}
summary = pd.DataFrame({k: v["detection_s"].describe(percentiles=[.5, .95]) for k, v in runs.items()}).T
print(summary.round(2).to_markdown())

samples = pd.read_csv("samples-7d.csv", parse_dates=["ts"])
hourly = samples.set_index("ts").groupby("device").resample("1h")["latency_ms"].mean()
```

Suggested tables and figures for the monograph:

* detection time box plot per configuration (Experiment 1);
* overhead vs number of devices - CPU %, memory, kbit/s (Experiment 2);
* false-positive count vs *k* under 10 %/20 % loss (Experiment 3);
* availability table and traffic heatmap exported from the Reports page.

## Threats to validity

* The Docker lab shares one kernel; latencies are lower and less variable than on physical
  networks. Repeat key runs on the VirtualBox lab.
* Wall-clock measurements include API polling granularity (0.25 s in the scripts).
* Overhead byte counts are estimates; validate with packet captures.
* Simulation-mode data (`NETMON_MONITOR_MODE=simulation`) is synthetic and must not be
  reported as measured network behaviour - use it only for scalability/overhead of the
  monitoring server itself.
