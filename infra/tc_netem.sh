#!/usr/bin/env bash
# tc_netem.sh — Apply / remove network emulation profiles
# Simulates realistic CSP latency on the client NIC
#
# Usage:
#   bash tc_netem.sh apply   — apply all three CSP profiles
#   bash tc_netem.sh remove  — remove all tc rules
#   bash tc_netem.sh status  — show current rules
#
# Profiles:
#   AWS/Japan  (port 8333): 2ms RTT / 0.5ms jitter / 1 Gbps
#   GCP/APAC   (port 8334): 80ms RTT / 5ms jitter / 100 Mbps
#   Azure/US   (port 8335): 180ms RTT / 10ms jitter / 50 Mbps
#
# Note: RTT is one-way delay × 2. Set delay = RTT/2.
#
# Author: Noah Kimaru | Kyoto Institute of Technology | 2026

NIC=${NIC:-eth0}
SERVER_IP="133.16.241.50"

apply() {
  echo "Applying tc netem rules on $NIC → $SERVER_IP ..."

  # Remove existing rules
  tc qdisc del dev "$NIC" root 2>/dev/null || true

  # Root HTB qdisc
  tc qdisc add dev "$NIC" root handle 1: htb default 30

  # AWS/Japan — port 8333: 1 Gbps, 1ms one-way delay (2ms RTT), 0.5ms jitter
  tc class add dev "$NIC" parent 1: classid 1:1 htb rate 1gbit burst 10mb
  tc qdisc add dev "$NIC" parent 1:1 handle 10: netem delay 1ms 500us distribution normal
  tc filter add dev "$NIC" parent 1: protocol ip u32 \
    match ip dst "$SERVER_IP" match ip dport 8333 0xffff \
    flowid 1:1

  # GCP/APAC — port 8334: 100 Mbps, 40ms one-way delay (80ms RTT), 5ms jitter
  tc class add dev "$NIC" parent 1: classid 1:2 htb rate 100mbit burst 2mb
  tc qdisc add dev "$NIC" parent 1:2 handle 20: netem delay 40ms 5ms distribution normal loss 0.01%
  tc filter add dev "$NIC" parent 1: protocol ip u32 \
    match ip dst "$SERVER_IP" match ip dport 8334 0xffff \
    flowid 1:2

  # Azure/US — port 8335: 50 Mbps, 90ms one-way delay (180ms RTT), 10ms jitter
  tc class add dev "$NIC" parent 1: classid 1:3 htb rate 50mbit burst 1mb
  tc qdisc add dev "$NIC" parent 1:3 handle 30: netem delay 90ms 10ms distribution normal loss 0.02%
  tc filter add dev "$NIC" parent 1: protocol ip u32 \
    match ip dst "$SERVER_IP" match ip dport 8335 0xffff \
    flowid 1:3

  echo "Done. Run 'bash tc_netem.sh status' to verify."
}

remove() {
  echo "Removing tc rules from $NIC ..."
  tc qdisc del dev "$NIC" root 2>/dev/null && echo "Removed." || echo "No rules to remove."
}

set_rtt() {
  # set_rtt <port> <rtt_ms> <jitter_ms> <bw_mbit>
  # Used by T16B sweep tests to override per-port delay
  local port=$1 rtt_ms=$2 jitter_ms=${3:-1} bw=${4:-100}
  local delay_ms=$(echo "$rtt_ms / 2" | bc -l | xargs printf "%.1f")
  echo "  Setting port $port → RTT=${rtt_ms}ms (delay=${delay_ms}ms), jitter=${jitter_ms}ms, bw=${bw}mbit"
  # Rebuild only the matching class — script-friendly, single port override
  case $port in
    8333) handle=10 classid=1:1 ;;
    8334) handle=20 classid=1:2 ;;
    8335) handle=30 classid=1:3 ;;
  esac
  tc qdisc change dev "$NIC" parent "$classid" handle "${handle}:" \
    netem delay "${delay_ms}ms" "${jitter_ms}ms" distribution normal
  tc class change dev "$NIC" parent 1: classid "$classid" htb rate "${bw}mbit" burst 2mb
}

sweep_rtt() {
  # sweep_rtt <port> <rtt_ms>  — sets all three ports to same RTT for T16B tests
  local rtt=$1
  local delay=$(echo "$rtt / 2" | bc -l | xargs printf "%.1f")
  for handle in 10 20 30; do
    tc qdisc change dev "$NIC" parent "1:$((handle/10))" handle "${handle}:" \
      netem delay "${delay}ms" 1ms distribution normal 2>/dev/null || true
  done
}

status() {
  echo "=== tc qdiscs ==="
  tc qdisc show dev "$NIC"
  echo "=== tc classes ==="
  tc class show dev "$NIC"
  echo "=== tc filters ==="
  tc filter show dev "$NIC"
}

tcp_tuning() {
  # Apply Big Fat Pipe / BDP-aware TCP settings
  # For 100 Mbps × 200ms RTT: BDP = 2.5 MB → use 128 MB buffers for headroom
  echo "Applying BDP-tuned TCP settings..."
  sysctl -w net.core.rmem_max=134217728
  sysctl -w net.core.wmem_max=134217728
  sysctl -w net.ipv4.tcp_rmem="4096 87380 134217728"
  sysctl -w net.ipv4.tcp_wmem="4096 65536 134217728"
  sysctl -w net.ipv4.tcp_congestion_control=bbr
  sysctl -w net.core.default_qdisc=fq
  sysctl -w net.ipv4.tcp_window_scaling=1
  sysctl -w net.ipv4.tcp_timestamps=1
  sysctl -w net.ipv4.tcp_sack=1
  echo "TCP tuning applied. Congestion control: $(sysctl -n net.ipv4.tcp_congestion_control)"
}

case "$1" in
  apply)   apply ;;
  remove)  remove ;;
  status)  status ;;
  set_rtt) set_rtt "$2" "$3" "${4:-1}" "${5:-100}" ;;
  sweep)   sweep_rtt "$2" ;;
  tcp)     tcp_tuning ;;
  *) echo "Usage: $0 {apply|remove|status|tcp|set_rtt <port> <rtt_ms>|sweep <rtt_ms>}" ;;
esac
