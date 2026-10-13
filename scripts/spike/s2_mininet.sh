#!/usr/bin/env bash
# Spike S2: does Mininet work here, with which datapath, and are tc modules usable?
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
echo "## mn version: $(mn --version 2>&1)"
mn -c >/dev/null 2>&1

for dp in kernel user; do
  echo; echo "## pingall, standalone OVS bridge, datapath=$dp"
  timeout 120 mn --controller=none --switch=ovsbr,datapath=$dp --topo=single,4 --test=pingall 2>&1 | grep -E "Results|rror|xception|dropped"
  echo "rc=$?"
  mn -c >/dev/null 2>&1
done

echo; echo "## topo_basic.py standalone pingall (explicit dpid, 4 hosts) datapath=auto"
"$REPO/.venv-core/bin/python" "$REPO/topo/topo_basic.py" --no-controller --test pingall 2>&1 | tail -3
mn -c >/dev/null 2>&1

echo; echo "## tc/netem/htb link shaping (mn --link tc), datapath=user"
timeout 120 mn --controller=none --switch=ovsbr,datapath=user --topo=single,2 --link=tc,bw=10,delay=5ms --test=pingall 2>&1 | grep -E "Results|rror|xception|dropped"
mn -c >/dev/null 2>&1

echo; echo "## tc modules"
for m in sch_htb sch_netem; do
  printf '%s: ' "$m"; (lsmod | grep -q "^$m" && echo loaded) || (modprobe -n $m >/dev/null 2>&1 && echo "available") || echo "not available"
done
