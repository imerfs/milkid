#!/bin/bash
# Installs the DNS watch service (dns-github-watch.py + its systemd unit) and the `milkid-update` command, and turns the
# older 5-minute DNS guard off. Run as root from the folder that holds the files:  bash install_dns_watch.sh
set -euo pipefail
cd "$(dirname "$0")"

# files copied from Windows may carry CRLF line endings, which bash, python and systemd cannot read
for f in dns-github-watch.py dns-github-watch.service milkid-update.sh; do
    sed -i 's/\r$//' "$f"
done

install -m 755 dns-github-watch.py /usr/local/bin/dns-github-watch.py
install -m 755 milkid-update.sh /usr/local/bin/milkid-update
install -m 644 dns-github-watch.service /etc/systemd/system/dns-github-watch.service

systemctl disable --now dns-github-guard.timer dns-github-guard.service 2>/dev/null || true
systemctl daemon-reload
systemctl enable --now dns-github-watch.service
echo "Installed. Waiting for the first measurements (about 40 seconds)..."
sleep 40
python3 /usr/local/bin/dns-github-watch.py status || true
