#!/usr/bin/env bash
# Spike S4: what does this OVS accept for flow monitoring? Uses ovs-ofctl's own monitor command so the
# result does not depend on Ryu. Creates and removes a throw-away bridge `fgmon`.
set -u
ovs-vsctl --if-exists del-br fgmon
ovs-vsctl add-br fgmon -- set bridge fgmon protocols=OpenFlow10,OpenFlow13,OpenFlow14
ovs-ofctl -O OpenFlow13 add-flow fgmon "table=0,priority=5,ip,cookie=0x1234,actions=goto_table:1"

for ver in OpenFlow14 OpenFlow13 OpenFlow10; do
  echo "## ovs-ofctl -O $ver monitor (4s) while a rule is modified, added and deleted"
  ( timeout 4 ovs-ofctl -O "$ver" monitor fgmon watch: 2>&1 & )
  sleep 1.2
  ovs-ofctl -O OpenFlow13 --strict mod-flows fgmon "table=0,priority=5,ip,actions=drop"
  sleep 0.5
  ovs-ofctl -O OpenFlow13 add-flow fgmon "table=0,priority=300,ip,nw_dst=10.0.0.3,actions=drop"
  sleep 0.5
  ovs-ofctl -O OpenFlow13 --strict del-flows fgmon "table=0,priority=300,ip,nw_dst=10.0.0.3"
  ovs-ofctl -O OpenFlow13 --strict add-flow fgmon "table=0,priority=5,ip,cookie=0x1234,actions=goto_table:1"
  sleep 3
  echo
done
ovs-vsctl del-br fgmon
echo "## ovs-vswitchd.log lines mentioning monitor / bad subtype (last 8)"
grep -iE "monitor|BAD_SUBTYPE" /var/log/openvswitch/ovs-vswitchd.log | tail -8
