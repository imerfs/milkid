#!/bin/bash
# Installs the DNS guard (dns-github-guard.sh plus its systemd service and timer).
# Run as root from the folder that holds the three files:  bash install_dns_guard.sh
set -euo pipefail
cd "$(dirname "$0")"

# files copied from Windows may carry CRLF line endings, which bash and systemd cannot read
for f in dns-github-guard.sh dns-github-guard.service dns-github-guard.timer; do
    sed -i 's/\r$//' "$f"
done

install -m 755 dns-github-guard.sh /usr/local/bin/dns-github-guard.sh
install -m 644 dns-github-guard.service /etc/systemd/system/dns-github-guard.service
install -m 644 dns-github-guard.timer /etc/systemd/system/dns-github-guard.timer

systemctl daemon-reload
systemctl enable --now dns-github-guard.timer
echo "Installed. Running one check now:"
systemctl start dns-github-guard.service || true
journalctl -t dns-github-guard -n 5 --no-pager || true
systemctl list-timers dns-github-guard.timer --no-pager
