#!/usr/bin/env bash
# Re-run every Phase 0 spike and store the raw evidence in docs/spike_evidence/ (needs root, ~10 minutes).
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EV="$REPO/docs/spike_evidence"
PY="$REPO/.venv-core/bin/python"
mkdir -p "$EV"
cd "$REPO"

echo "[spike] S1 datapath";             bash scripts/spike/s1_datapath.sh > "$EV/s1_datapath.txt" 2>&1
echo "[spike] S2 mininet";              bash scripts/spike/s2_mininet.sh  > "$EV/s2_mininet.txt" 2>&1
echo "[spike] S3a OF1.4 flow monitor";  "$PY" scripts/spike/s3_flowmon_measure.py --mode of14 --trials 5 > "$EV/s3_of14_summary.txt" 2>&1
echo "[spike] S3b NXST over OF1.3";     "$PY" scripts/spike/s3_flowmon_measure.py --mode nxst13 --trials 5 > "$EV/s3_nxst13_summary.txt" 2>&1
echo "[spike] S3c NXST over OF1.0 (kernel datapath)"
"$PY" scripts/spike/s3_flowmon_measure.py --mode ofctl_monitor --trials 30 > "$EV/s3_ofctl_monitor_summary.txt" 2>&1
echo "[spike] S3d NXST over OF1.0 (userspace datapath)"
"$PY" scripts/spike/s3_flowmon_measure.py --mode ofctl_monitor --trials 10 --datapath user --tag _userspace > "$EV/s3_ofctl_monitor_userspace_summary.txt" 2>&1
echo "[spike] S4 ovs-ofctl monitor CLI"; bash scripts/spike/s4_ovs_monitor_cli.sh > "$EV/s4_ovs_monitor_cli.txt" 2>&1
echo "[spike] two-switch standalone";   "$PY" topo/topo_basic.py --two-switch --no-controller --test pingall > "$EV/s2_two_switch_standalone.txt" 2>&1
echo "[spike] doctor";                  python3 scripts/doctor.py --no-color > "$EV/doctor.txt" 2>&1
echo "[spike] done. Evidence in $EV"
