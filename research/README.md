# Research experiments

Scripts that produce the measurements for the evaluation chapter. The full methodology
(research question, metrics, analytical model, experiment matrix, analysis) is in
[docs/research.md](../docs/research.md).

| Script | Measures |
|---|---|
| `measure_detection.py` | Failure detection time, status-change time, recovery-detection time, detection rate |
| `measure_overhead.py` | Polls/min, probe packets/s, SNMP requests/s, estimated monitoring bandwidth, server CPU and memory - optionally while scaling the device count |
| `netmon_api.py` | Dependency-free API client used by the scripts (and `lab/setup_lab.py`) |

The scripts only need Python 3.11+ (standard library). Results are written as CSV to
`research/results/` (git-ignored).

```bash
# 1. start NetMon with the virtual lab and register the lab devices
make lab
python3 lab/setup_lab.py --password '<admin password>' --poll-interval 10

# 2. detection time: 30 injected outages of the lab database server
python3 research/measure_detection.py --password '<admin password>' \
    --device "Lab DB Server" --container netmon-lab-db-1 --trials 30

# 3. monitoring overhead with 100 extra (simulated) devices for 5 minutes
python3 research/measure_overhead.py --password '<admin password>' --add-devices 100 --cleanup
```
