#!/bin/bash
# Update the site from GitHub: make sure GitHub is reachable (trying another DNS when it is not), pull, migrate,
# collect static files, restart. Installed as /usr/local/bin/milkid-update by deploy/install_dns_watch.sh; run it as root.
set -uo pipefail
cd /opt/milkid || exit 1
WATCH=/usr/local/bin/dns-github-watch.py
# a stalled connection fails after 15 s instead of hanging for minutes
GIT=(git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=15)

pulled=0
for attempt in 1 2 3 4 5; do
    if [ "$attempt" -eq 1 ]; then python3 "$WATCH" ensure || true; else python3 "$WATCH" ensure --switch || true; fi
    if "${GIT[@]}" pull origin main; then pulled=1; break; fi
    echo "git pull failed (attempt $attempt of 5); trying another DNS..."
done
if [ "$pulled" -ne 1 ]; then
    echo "GitHub could not be reached. Send the code from your computer instead (git archive + scp, see docs/operations.md)."
    exit 1
fi
venv/bin/python manage.py migrate \
    && venv/bin/python manage.py collectstatic --noinput \
    && systemctl restart milkid \
    && systemctl is-active milkid
