#!/usr/bin/env bash
# One-shot deploy of MelkID on a fresh Ubuntu/Debian server (run as root).
# Usage: bash server_setup.sh [domain-or-ip]   (default: server's public IP)
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/imerfs/milkid.git}"
BRANCH="${BRANCH:-ccr-6a10cb3f-dspz6o}"
APP_DIR=/opt/milkid
HOST_NAME="${1:-$(curl -s4 ifconfig.me || hostname -I | awk '{print $1}')}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-dev build-essential libmagic1 libjpeg-dev zlib1g-dev nginx git curl

if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch origin "$BRANCH" && git -C "$APP_DIR" checkout "$BRANCH" && git -C "$APP_DIR" pull origin "$BRANCH"
else
  git clone -b "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

if [ ! -f .env ]; then
  SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(64))')
  SCHEME_SECURE=False
  cat > .env <<ENV
DJANGO_SECRET_KEY=$SECRET
DEBUG=False
REPLIT_DOMAINS=$HOST_NAME
USE_POSTGRES=False
COOKIE_SECURE=$SCHEME_SECURE
SECURE_SSL_REDIRECT=False
ENV
  chmod 600 .env
fi

./venv/bin/python manage.py migrate --noinput
./venv/bin/python manage.py collectstatic --noinput
mkdir -p media
chown -R www-data:www-data "$APP_DIR"

cat > /etc/systemd/system/milkid.service <<UNIT
[Unit]
Description=MelkID (gunicorn)
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/gunicorn django_project.wsgi:application --bind 127.0.0.1:8000 --workers 3 --timeout 60
Restart=always

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/nginx/sites-available/milkid <<NGINX
server {
    listen 80 default_server;
    server_name $HOST_NAME _;
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
command -v ufw >/dev/null && ufw status | grep -q active && ufw allow 80,443/tcp || true

echo
echo "Done. Site: http://$HOST_NAME/"
echo "Create admin:  cd $APP_DIR && ./venv/bin/python manage.py createsuperuser"
