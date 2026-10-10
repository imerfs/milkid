#!/usr/bin/env bash
# Hardens a MelkID server (Ubuntu 24.04, run as root, AFTER server_setup.sh and certbot):
#   * nftables firewall: only 22/80/443 open; 443 and SSH Iran-only; per-IP flood limits
#   * nginx: Iran-only (except the Let's Encrypt challenge), rate/connection limits,
#            slow-client timeouts, private /media/, unknown hosts dropped
#   * kernel (SYN-flood) sysctls, fail2ban, sshd tightening, systemd sandboxing
#
# Usage:   bash harden_server.sh amirl.ir
# Options (env): ADMIN_IPS="1.2.3.4 5.6.7.8"   extra IPs always allowed (SSH + web)
#                SSH_IRAN_ONLY=0               leave SSH open to the world (still rate-limited)
set -euo pipefail

DOMAIN="${1:-}"
[[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] || { echo "Usage: bash harden_server.sh <domain>"; exit 1; }
APP_DIR=/opt/milkid
SSH_IRAN_ONLY="${SSH_IRAN_ONLY:-1}"
ADMIN_IPS="${ADMIN_IPS:-}"
[ -n "${SSH_CLIENT:-}" ] && ADMIN_IPS="$ADMIN_IPS ${SSH_CLIENT%% *}"   # never lock out the current session
ADMIN_IPS=$(echo "$ADMIN_IPS" | tr ' ' '\n' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | sort -u | paste -sd, - || true)

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y nftables fail2ban curl

# ---------------------------------------------------------------- Iran IP list
install -d /etc/milkid
cat > /usr/local/sbin/milkid-update-geo <<'UPD'
#!/usr/bin/env bash
# Refresh the Iran IPv4 ranges used by nginx and nftables (kept if the download fails).
set -euo pipefail
TMP=$(mktemp)
curl -fsS --max-time 60 https://www.ipdeny.com/ipblocks/data/aggregated/ir-aggregated.zone -o "$TMP"
grep -qE '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$' "$TMP" || { echo "bad geo list"; exit 1; }
[ "$(wc -l < "$TMP")" -gt 200 ] || { echo "geo list suspiciously short"; exit 1; }
grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$' "$TMP" | sort -u > /etc/milkid/ir.zone
rm -f "$TMP"
sed 's|$| 1;|' /etc/milkid/ir.zone > /etc/nginx/geo-ir.conf
if [ -f /etc/nftables.d/milkid.nft ]; then
  /usr/local/sbin/milkid-build-nft && nft -f /etc/nftables.d/milkid.nft
fi
nginx -t -q && systemctl reload nginx
UPD
chmod 755 /usr/local/sbin/milkid-update-geo

# nft ruleset generator (reads /etc/milkid/ir.zone and /etc/milkid/nft.env)
cat > /usr/local/sbin/milkid-build-nft <<'BLD'
#!/usr/bin/env bash
set -euo pipefail
. /etc/milkid/nft.env
install -d /etc/nftables.d
IRAN=$(paste -sd, /etc/milkid/ir.zone)
ADMIN_SET=${ADMIN_IPS:-127.0.0.1}
if [ "$SSH_IRAN_ONLY" = "1" ]; then SSH_RULE='ip saddr @iran4 tcp dport 22 ct state new meter ssh_flood { ip saddr limit rate 6/minute burst 6 packets } accept'
else SSH_RULE='tcp dport 22 ct state new meter ssh_flood { ip saddr limit rate 6/minute burst 6 packets } accept'; fi
cat > /etc/nftables.d/milkid.nft <<NFT
table inet milkid
delete table inet milkid
table inet milkid {
  set iran4 { type ipv4_addr; flags interval; auto-merge; elements = { $IRAN } }
  set admin4 { type ipv4_addr; flags interval; elements = { $ADMIN_SET } }
  chain input {
    type filter hook input priority -10; policy drop;
    iif lo accept
    ct state invalid drop
    ct state established,related accept
    meta l4proto icmp icmp type echo-request limit rate 5/second accept
    meta l4proto ipv6-icmp accept
    ip saddr @admin4 tcp dport { 22, 80, 443 } accept
    $SSH_RULE
    # 80 stays world-open: Let's Encrypt validates from outside Iran. nginx geo-blocks everything else there.
    tcp dport 80 ct state new meter http_flood { ip saddr limit rate 40/second burst 80 packets } accept
    ip saddr @iran4 tcp dport 443 ct state new meter https_flood { ip saddr limit rate 40/second burst 80 packets } accept
  }
}
NFT
BLD
chmod 755 /usr/local/sbin/milkid-build-nft
cat > /etc/milkid/nft.env <<ENV
ADMIN_IPS="$ADMIN_IPS"
SSH_IRAN_ONLY=$SSH_IRAN_ONLY
ENV

# weekly refresh
cat > /etc/cron.weekly/milkid-geo <<'CRON'
#!/bin/sh
/usr/local/sbin/milkid-update-geo || logger -t milkid "geo list update failed"
CRON
chmod 755 /etc/cron.weekly/milkid-geo

# initial list (needed before nginx -t); abort rather than lock everyone out
touch /etc/nginx/geo-ir.conf
/usr/local/sbin/milkid-update-geo || { echo "Could not download the Iran IP list - aborting (nothing locked)."; exit 1; }

# ---------------------------------------------------------------- nginx
cat > /etc/nginx/conf.d/milkid-security.conf <<'NGX'
server_tokens off;
geo $ir_ip { default 0; 127.0.0.1/32 1; include /etc/nginx/geo-ir.conf; }
map $uri $acme_path { default 0; ~^/\.well-known/acme-challenge/ 1; }
map "$ir_ip$acme_path" $geo_allowed { "00" 0; default 1; }
limit_req_zone  $binary_remote_addr zone=milkid_req:10m   rate=15r/s;
limit_req_zone  $binary_remote_addr zone=milkid_login:10m rate=30r/m;
limit_conn_zone $binary_remote_addr zone=milkid_conn:10m;
limit_req_status 429;
limit_conn_status 429;
client_header_timeout 10s;
client_body_timeout 15s;
send_timeout 20s;
keepalive_timeout 15s;
reset_timedout_connection on;
client_header_buffer_size 2k;
large_client_header_buffers 4 8k;
NGX

install -d /etc/nginx/snippets
cat > /etc/nginx/snippets/milkid-protect.conf <<'NGX'
if ($geo_allowed = 0) { return 444; }
limit_req zone=milkid_req burst=40 nodelay;
limit_conn milkid_conn 30;
NGX

cat > /etc/nginx/snippets/milkid-proxy.conf <<'NGX'
proxy_pass http://127.0.0.1:8000;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_connect_timeout 5s;
proxy_read_timeout 60s;
NGX

cat > /etc/nginx/snippets/milkid-locations.conf <<NGX
client_max_body_size 20M;
location ~ /\.(?!well-known) { return 404; }
location /static/ { alias $APP_DIR/staticfiles/; add_header Cache-Control "no-cache"; }
# nginx asks Django whether the visitor is signed in before serving private uploads
location = /_media-auth/ {
    internal;
    proxy_pass http://127.0.0.1:8000/_media-auth/;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-Proto \$scheme;
}
location ^~ /media/property_ads/ { alias $APP_DIR/media/property_ads/; add_header X-Content-Type-Options nosniff; }
location /media/ {
    auth_request /_media-auth/;
    alias $APP_DIR/media/;
    add_header X-Content-Type-Options nosniff;
    add_header Content-Security-Policy "default-src 'none'; sandbox";
    add_header Cache-Control "private, no-store";
}
location /login/ {
    limit_req zone=milkid_login burst=10 nodelay;
    include snippets/milkid-proxy.conf;
}
location / { include snippets/milkid-proxy.conf; }
NGX

CERT=/etc/letsencrypt/live/$DOMAIN
if [ -f "$CERT/fullchain.pem" ]; then
cat > /etc/nginx/sites-available/milkid <<NGX
server { listen 80 default_server; server_name _; return 444; }
server { listen 443 ssl default_server; ssl_reject_handshake on; }
server {
    listen 80;
    server_name $DOMAIN;
    include snippets/milkid-protect.conf;
        location / { return 301 https://\$host\$request_uri; }
}
server {
    listen 443 ssl http2;
    server_name $DOMAIN;
    ssl_certificate $CERT/fullchain.pem;
    ssl_certificate_key $CERT/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
    include snippets/milkid-protect.conf;
    include snippets/milkid-locations.conf;
}
NGX
else
echo "NOTE: no certificate for $DOMAIN yet - serving HTTP only. Run certbot, then re-run this script."
cat > /etc/nginx/sites-available/milkid <<NGX
server { listen 80 default_server; server_name _; return 444; }
server {
    listen 80;
    server_name $DOMAIN;
    include snippets/milkid-protect.conf;
    include snippets/milkid-locations.conf;
}
NGX
fi
ln -sf /etc/nginx/sites-available/milkid /etc/nginx/sites-enabled/milkid
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

# ---------------------------------------------------------------- app service sandbox
install -d /etc/systemd/system/milkid.service.d
cat > /etc/systemd/system/milkid.service.d/harden.conf <<UNIT
[Service]
ExecStart=
ExecStart=$APP_DIR/venv/bin/gunicorn django_project.wsgi:application --bind 127.0.0.1:8000 --workers 3 --threads 4 --worker-class gthread --timeout 60 --max-requests 1000 --max-requests-jitter 100 --limit-request-line 4094 --limit-request-fields 50
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
UNIT
chmod 600 "$APP_DIR/.env" 2>/dev/null || true
chown www-data:www-data "$APP_DIR/.env" 2>/dev/null || true
systemctl daemon-reload
systemctl restart milkid

# ---------------------------------------------------------------- kernel (flood resistance)
cat > /etc/sysctl.d/99-milkid.conf <<'SYS'
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_max_syn_backlog = 4096
net.ipv4.tcp_synack_retries = 2
net.ipv4.tcp_rfc1337 = 1
net.core.somaxconn = 4096
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.icmp_ignore_bogus_error_responses = 1
kernel.dmesg_restrict = 1
SYS
sysctl --system >/dev/null

# ---------------------------------------------------------------- sshd + fail2ban
cat > /etc/ssh/sshd_config.d/99-milkid.conf <<'SSH'
MaxAuthTries 3
LoginGraceTime 20
MaxStartups 5:50:20
X11Forwarding no
AllowAgentForwarding no
SSH
sshd -t && systemctl reload ssh

cat > /etc/fail2ban/jail.d/milkid.local <<'F2B'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 4
banaction = nftables
[sshd]
enabled = true
[recidive]
enabled = true
bantime = 1w
F2B
systemctl enable --now fail2ban
systemctl restart fail2ban

# ---------------------------------------------------------------- firewall (with automatic rollback)
/usr/local/sbin/milkid-build-nft
nft -c -f /etc/nftables.d/milkid.nft
echo 'include "/etc/nftables.d/*.nft"' > /etc/nftables.conf
systemctl enable nftables >/dev/null 2>&1 || true
nft -f /etc/nftables.d/milkid.nft
echo
echo "Firewall applied. Open a SECOND terminal and confirm you can still ssh in and load https://$DOMAIN"
read -r -t 90 -p "Type YES within 90 s to keep the firewall (otherwise it is removed): " ANS || ANS=""
if [ "${ANS^^}" != "YES" ]; then
  nft delete table inet milkid
  rm -f /etc/nftables.d/milkid.nft
  echo "Rolled back: firewall removed. Everything else stays applied."
  exit 1
fi
echo "Done. Allowed ports: 22 (Iran + $ADMIN_IPS), 80 (world, nginx geo-filtered), 443 (Iran)."
