#!/bin/bash
# Keeps the server on a DNS that can actually reach github.com (the server has no direct foreign internet access).
# Every run: if github.com answers with the current DNS, do nothing; otherwise try the list below in order and keep the
# first one that works. If none works, go back to the network's own DNS so the rest of the server keeps resolving.
#
# Needs systemd-resolved (Ubuntu default), curl and root. Installed by deploy/install_dns_guard.sh (runs every 5 minutes).

# One entry per line: the DNS servers of one provider, in the order they are tried.
SERVERS=(
    "78.157.42.100 78.157.42.101"      # Electro
    "10.202.10.202 10.202.10.102"      # 403.online
    "10.202.10.10 10.202.10.11"        # Radar Game
    "178.22.122.100 185.51.200.2"      # Shecan
    "185.55.226.26 185.55.225.25"      # Begzar
    "85.15.1.14 85.15.1.15"            # Shatel
)
CHECK_URL="https://github.com"
TIMEOUT=8

IFACE=$(ip -o route get 1.1.1.1 2>/dev/null | sed -n 's/.* dev \([^ ]*\).*/\1/p')
[ -n "$IFACE" ] || { logger -t dns-github-guard "no network interface found"; exit 1; }

log() { logger -t dns-github-guard "$*"; echo "$*"; }

# true when github.com answers with a normal web response through the current DNS
works() {
    resolvectl flush-caches
    local code
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" "$CHECK_URL")
    [[ "$code" =~ ^(200|301|302)$ ]]
}

if works; then
    exit 0
fi

log "github.com is not reachable with the current DNS; trying the list"
for servers in "${SERVERS[@]}"; do
    resolvectl dns "$IFACE" $servers
    resolvectl default-route "$IFACE" yes
    if works; then
        log "switched to: $servers"
        exit 0
    fi
done

resolvectl revert "$IFACE"
resolvectl flush-caches
log "none of the listed DNS servers reached github.com; back to the network's own DNS"
exit 1
