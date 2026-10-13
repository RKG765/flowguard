#!/usr/bin/env bash
# Spike S1: which Open vSwitch datapath works here, kernel module or userspace (netdev)?
# Prints evidence only; creates and removes throw-away bridges named fgspike-*.
set -u
echo "## kernel: $(uname -r)"
echo "## modules dir:"; ls /lib/modules 2>&1 | head
echo "## modprobe openvswitch (real attempt):"; modprobe -v openvswitch 2>&1; echo "modprobe rc=$?"
echo "## /sys/module/openvswitch present: $([ -d /sys/module/openvswitch ] && echo yes || echo no)"
echo "## lsmod | grep openvswitch:"; lsmod | grep -i openvswitch || echo "(not loaded)"
echo "## ovs-vsctl --version:"; ovs-vsctl --version | head -1
echo "## existing datapaths:"; ovs-appctl dpif/dump-dps 2>&1

echo; echo "## TEST A: bridge with default (kernel) datapath"
ovs-vsctl --timeout=10 --if-exists del-br fgspike-k
if timeout 20 ovs-vsctl --timeout=10 add-br fgspike-k; then
  sleep 1
  ovs-appctl dpif/show 2>&1
  ovs-vsctl get bridge fgspike-k datapath_type
  echo "kernel_bridge_result=created"
else
  echo "kernel_bridge_result=failed"
fi
ovs-vsctl --timeout=10 --if-exists del-br fgspike-k

echo; echo "## TEST B: bridge with userspace datapath (datapath_type=netdev)"
ovs-vsctl --timeout=10 --if-exists del-br fgspike-u
if timeout 20 ovs-vsctl --timeout=10 add-br fgspike-u -- set bridge fgspike-u datapath_type=netdev; then
  sleep 1
  ovs-appctl dpif/show 2>&1
  ovs-vsctl get bridge fgspike-u datapath_type
  echo "userspace_bridge_result=created"
else
  echo "userspace_bridge_result=failed"
fi
ovs-vsctl --timeout=10 --if-exists del-br fgspike-u

echo; echo "## ovs-vswitchd.log (last 15 lines mentioning datapath/module/dpif):"
grep -iE 'datapath|module|dpif|netdev' /var/log/openvswitch/ovs-vswitchd.log 2>/dev/null | tail -15
