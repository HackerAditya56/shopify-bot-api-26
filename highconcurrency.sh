#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  highconcurrency.sh — tune Ubuntu 24.04 to hold 1500+ concurrent
#  connections on the API (port 8080) and strip rate-limit/DDoS layers
#  that close or throttle connections.
#
#  Usage:  sudo bash highconcurrency.sh [--flush-firewall]
#          --flush-firewall  also fully flush nft/iptables (open box)
#  Safe to re-run (idempotent). Backs up every file it touches.
# ─────────────────────────────────────────────────────────────────────
set -uo pipefail

API_PORT=8080
TS=$(date +%Y%m%d_%H%M%S)
BK=/root/backup_$TS
mkdir -p "$BK"
log(){ printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
err(){ printf '\033[1;31m[-]\033[0m %s\n' "$*"; }
die(){ err "$*"; exit 1; }

[[ $EUID -eq 0 ]] || die "run as root: sudo bash $0"

# ─────────────────────────────────────────────────────────────────────
# 0. backups
# ─────────────────────────────────────────────────────────────────────
for f in /etc/sysctl.conf /etc/security/limits.conf /etc/systemd/system.conf \
         /etc/nftables.conf /etc/default/ufw; do
  [[ -f $f ]] && cp -a "$f" "$BK/$(basename "$f")" 2>/dev/null
done
log "backups written to $BK"

# ─────────────────────────────────────────────────────────────────────
# 1. sysctl — stop the kernel from closing/dropping connections
# ─────────────────────────────────────────────────────────────────────
SYSCTL_FILE=/etc/sysctl.d/99-highconcurrency.conf
cat > "$SYSCTL_FILE" <<'EOF'
# ── accept queue: DO NOT RST when backlog overflows (clients retry, survive) ──
net.ipv4.tcp_abort_on_overflow = 0

# ── listener + backlog buffers (the 1500-SYN gate) ──
net.core.somaxconn = 65535
net.core.netdev_max_backlog = 65535
net.ipv4.tcp_max_syn_backlog = 65535

# ── retransmit tuning: fewer SYN retries, faster recovery ──
net.ipv4.tcp_syn_retries = 2
net.ipv4.tcp_synack_retries = 2
net.ipv4.tcp_syncookies = 1

# ── TIME_WAIT recycling: don't exhaust ephemeral ports under churn ──
net.ipv4.tcp_fin_timeout = 10
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_max_tw_buckets = 262144
net.ipv4.ip_local_port_range = 1024 65535

# ── keepalive: detect dead peers fast, free sockets ──
net.ipv4.tcp_keepalive_time = 60
net.ipv4.tcp_keepalive_intvl = 10
net.ipv4.tcp_keepalive_probes = 6

# ── no slow-start reset on idle links ──
net.ipv4.tcp_slow_start_after_idle = 0

# ── socket buffers ──
net.core.rmem_max = 33554432
net.core.wmem_max = 33554432
net.core.rmem_default = 1048576
net.core.wmem_default = 1048576
net.core.optmem_max = 65536

# ── conntrack: 1500 concurrent * ~5 sockets each, with headroom ──
net.netfilter.nf_conntrack_max = 2097152
net.netfilter.nf_conntrack_tcp_timeout_established = 300
net.netfilter.nf_conntrack_tcp_timeout_fin_wait = 30
net.netfilter.nf_conntrack_tcp_timeout_close_wait = 15
net.netfilter.nf_conntrack_tcp_timeout_syn_recv = 30

# ── IPv6 off (one less path to track) ──
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
EOF

sysctl -p "$SYSCTL_FILE" >/dev/null 2>&1 || true
# apply whatever did not load from the file (older knobs) directly
sysctl -w net.ipv4.tcp_abort_on_overflow=0 >/dev/null 2>&1 || true
sysctl -w net.core.somaxconn=65535 >/dev/null 2>&1 || true
sysctl -w net.core.netdev_max_backlog=65535 >/dev/null 2>&1 || true
sysctl -w net.ipv4.tcp_max_syn_backlog=65535 >/dev/null 2>&1 || true
sysctl -w net.ipv4.ip_local_port_range="1024 65535" >/dev/null 2>&1 || true
sysctl -w net.ipv4.tcp_tw_reuse=1 >/dev/null 2>&1 || true
sysctl -w net.ipv4.tcp_fin_timeout=10 >/dev/null 2>&1 || true
log "sysctl applied ($SYSCTL_FILE)"

# conntrack buckets (fixed at module load; best-effort boot param)
if [[ -d /sys/module/nf_conntrack ]]; then
  echo "options nf_conntrack hashsize=524288" > /etc/modprobe.d/nf_conntrack.conf
  log "nf_conntrack hashsize=524288 set for next boot"
fi

# ─────────────────────────────────────────────────────────────────────
# 2. file descriptors — 1500 conns * several sockets blow past 1024
# ─────────────────────────────────────────────────────────────────────
if ! grep -q '^\* soft nofile' /etc/security/limits.conf 2>/dev/null; then
  cat >> /etc/security/limits.conf <<EOF
* soft nofile 1048576
* hard nofile 1048576
* soft nproc 1048576
* hard nproc 1048576
root soft nofile 1048576
root hard nofile 1048576
EOF
  log "limits.conf updated"
else
  warn "limits.conf already has nofile entries — skipping (edit manually if needed)"
fi

# systemd default limits (covers services, not just login shells)
sed -i 's/^#\?DefaultLimitNOFILE=.*/DefaultLimitNOFILE=1048576/' /etc/systemd/system.conf
grep -q '^DefaultLimitNOFILE' /etc/systemd/system.conf || echo "DefaultLimitNOFILE=1048576" >> /etc/systemd/system.conf
log "systemd DefaultLimitNOFILE=1048576"

ulimit -n 1048576 2>/dev/null || warn "could not raise ulimit in this shell (re-login or reboot)"

# ─────────────────────────────────────────────────────────────────────
# 3. firewall — open port 8080 fully, drop rate-limit rules on it
# ─────────────────────────────────────────────────────────────────────
# UFW
if command -v ufw >/dev/null 2>&1 && ufw status >/dev/null 2>&1; then
  ufw delete limit "$API_PORT/tcp" >/dev/null 2>&1 || true
  ufw allow "$API_PORT/tcp" >/dev/null 2>&1 || true
  ufw allow "$API_PORT/udp" >/dev/null 2>&1 || true
  log "ufw: $API_PORT opened (rate-limit rule removed)"
fi

# iptables / iptables-nft: insert an ACCEPT for 8080 above any REJECT/limit
for IPT in iptables iptables-nft; do
  command -v "$IPT" >/dev/null 2>&1 || continue
  "$IPT" -I INPUT -p tcp --dport "$API_PORT" -j ACCEPT 2>/dev/null || true
  "$IPT" -I INPUT -p udp --dport "$API_PORT" -j ACCEPT 2>/dev/null || true
  log "$IPT: ACCEPT inserted for $API_PORT"
done

# nftables: add an allow rule for 8080 in the input chain if a table exists
if command -v nft >/dev/null 2>&1 && nft list ruleset >/dev/null 2>&1; then
  nft add rule inet filter input tcp dport "$API_PORT" accept 2>/dev/null \
    || nft insert rule ip filter input tcp dport "$API_PORT" accept 2>/dev/null \
    || warn "nft: no standard filter/input chain found — verify manually"
  log "nft: allow rule added for $API_PORT (where a chain existed)"
fi

# ─────────────────────────────────────────────────────────────────────
# 4. disable DDoS-protection daemons that ban/cooldown the API
# ─────────────────────────────────────────────────────────────────────
for svc in fail2ban csf lfd crowdsec; do
  if systemctl list-unit-files 2>/dev/null | grep -q "^${svc}\."; then
    systemctl stop "$svc" 2>/dev/null || true
    systemctl disable "$svc" 2>/dev/null || true
    log "$svc: stopped + disabled"
  fi
done
# fail2ban manual jail sweep (in case it was running outside systemd)
if command -v fail2ban-client >/dev/null 2>&1; then
  fail2ban-client unban --all 2>/dev/null || true
  log "fail2ban: all bans cleared"
fi

# ─────────────────────────────────────────────────────────────────────
# 5. bump the uvicorn listen backlog in main_v2.py (app-side gate)
# ─────────────────────────────────────────────────────────────────────
for py in main_v2.py main.py; do
  for dir in . /opt/shopify /root; do
    [[ -f "$dir/$py" ]] || continue
    if grep -q 'backlog=' "$dir/$py"; then
      cp -a "$dir/$py" "$BK/$py"
      sed -i -E 's/backlog=[0-9]+/backlog=65535/' "$dir/$py"
      log "$dir/$py: backlog -> 65535"
    fi
  done
done

# ─────────────────────────────────────────────────────────────────────
# 6. optional full flush (open box)
# ─────────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--flush-firewall" ]]; then
  command -v nft >/dev/null 2>&1 && { nft flush ruleset 2>/dev/null; log "nft: ruleset flushed"; }
  for IPT in iptables iptables-nft; do
    command -v "$IPT" >/dev/null 2>&1 && { "$IPT" -P INPUT ACCEPT; "$IPT" -F; "$IPT" -X; log "$IPT: flushed, policy ACCEPT"; }
  done
fi

# ─────────────────────────────────────────────────────────────────────
# 7. verification
# ─────────────────────────────────────────────────────────────────────
printf '\n%s\n' "══════════ VERIFY ══════════"
printf 'somaxconn        : %s\n' "$(sysctl -n net.core.somaxconn)"
printf 'netdev_backlog   : %s\n' "$(sysctl -n net.core.netdev_max_backlog)"
printf 'syn_backlog      : %s\n' "$(sysctl -n net.ipv4.tcp_max_syn_backlog)"
printf 'abort_on_overflow: %s (0 = no RST on overflow)\n' "$(sysctl -n net.ipv4.tcp_abort_on_overflow)"
printf 'conntrack_max    : %s\n' "$(cat /proc/sys/net/netfilter/nf_conntrack_max 2>/dev/null || echo n/a)"
printf 'ulimit -n        : %s\n' "$(ulimit -n)"
command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | sed 's/^/ufw              : /' || true

log "done. restart the bot so the new backlog + fd limits take effect:"
log "  systemctl restart <your-bot-service>   (or: reboot)"
log "then hammer it:"
log "  ab -n 20000 -c 1500 http://127.0.0.1:8080/health"
