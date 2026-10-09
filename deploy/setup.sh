#!/usr/bin/env bash
# Deploy MelkID on a fresh Ubuntu/Debian server (run as root).
# Usage: bash setup.sh [domain]    (without a domain, the server IP is used)
set -euo pipefail

REPO=https://github.com/imerfs/milkid
BRANCH=${BRANCH:-main}
APP_DIR=/opt/milkid
HOST=${1:-$(curl -s https://api.ipify.org || hostname -I | awk '{print $1}')}

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-dev build-essential \
  libpq-dev libmagic1 nginx git curl

if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch origin "$BRANCH" && git -C "$APP_DIR" checkout "$BRANCH" && git -C "$APP_DIR" pull origin "$BRANCH"
else
  git clone -b "$BRANCH" "$REPO" "$APP_DIR"
fi
cd "$APP_DIR"

python3 -m venv venv
./venv/bin/pip install -U pip
./venv/bin/pip install -r requirements.txt gunicorn

if [ ! -f .env ]; then
  cat > .env <<ENV
DJANGO_SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(50))')
DEBUG=False
REPLIT_DOMAINS=$HOST
USE_POSTGRES=False
SECURE_SSL_REDIRECT=False
USE_HTTPS=False
ENV
  chmod 600 .env
fi

set -a; . ./.env; set +a
./venv/bin/python manage.py migrate --noinput
./venv/bin/python manage.py collectstatic --noinput
mkdir -p media && chown -R www-data:www-data media "$APP_DIR"/db.sqlite3 "$APP_DIR" 2>/dev/null || true

cat > /etc/systemd/system/milkid.service <<UNIT
[Unit]
Description=MelkID gunicorn
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/gunicorn django_project.wsgi:application --bind 127.0.0.1:8000 --workers 3
Restart=always

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/nginx/sites-available/milkid <<NGINX
server {
    listen 80;
    server_name $HOST;
    client_max_body_size 20M;
    location /static/ { alias $APP_DIR/staticfiles/; }
    location /media/  { alias $APP_DIR/media/; }
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGINX
ln -sf /etc/nginx/sites-available/milkid /etc/nginx/sites-enabled/milkid
rm -f /etc/nginx/sites-enabled/default
nginx -t

systemctl daemon-reload
systemctl enable --now milkid
systemctl restart milkid nginx

echo "Done: http://$HOST"
echo "Create admin: cd $APP_DIR && set -a && . ./.env && ./venv/bin/python manage.py createsuperuser"
