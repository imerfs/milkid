# Operations: deploy, backups, monitoring

## Two ways to run the site
- **Today (systemd + nginx + SQLite)**: `deploy/server_setup.sh`, then `git pull`, `migrate`, `collectstatic`, `systemctl restart milkid`.
- **Docker (web + PostgreSQL + nginx)**: `cp .env.docker.example .env`, edit it, `docker compose up -d --build`.
  Update with `git pull && docker compose up -d --build` (migrations and `collectstatic` run on start).

## Backups
`python manage.py backup_db [--media] [--keep 14] [--dir PATH]` writes a timestamped copy and deletes the oldest.
SQLite copies are integrity-checked and gzipped; PostgreSQL uses `pg_dump --format=custom`.

Nightly on the bare server:
```bash
cp /opt/milkid/deploy/milkid-backup.service /opt/milkid/deploy/milkid-backup.timer /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now milkid-backup.timer
systemctl list-timers milkid-backup.timer
```
Backups land in `/opt/milkid/backups/`. **Also copy them off the server** (another machine or storage): a backup on the same disk
dies with the disk. Example from your own computer: `scp root@SERVER:/opt/milkid/backups/db-*.gz .`

### Restore drill (do it once, then every month, and write down how long it took)
SQLite:
```bash
systemctl stop milkid
cp /opt/milkid/db.sqlite3 /root/db.sqlite3.before-restore
gunzip -c /opt/milkid/backups/db-YYYYMMDD-HHMMSS.sqlite3.gz > /opt/milkid/db.sqlite3
chown www-data:www-data /opt/milkid/db.sqlite3
systemctl start milkid && curl -fsS http://127.0.0.1:8000/healthz/
```
PostgreSQL (Docker): `docker compose exec -T db pg_restore -U melkid -d melkid --clean --if-exists < backups/db-YYYYMMDD-HHMMSS.dump`

## Monitoring
- `GET /healthz/` answers `{"status":"ok"}` (200) or 503 when the database is unreachable. Point an uptime monitor at it.
- `docker compose --profile monitoring up -d` starts Uptime Kuma on `127.0.0.1:3001`; open it through an SSH tunnel
  (`ssh -L 3001:127.0.0.1:3001 root@SERVER`) and add an HTTP check for `http://nginx/healthz/` plus a notification channel.
- `LOG_FORMAT=json` prints one JSON object per log line (Docker sets it). `docker compose logs -f web`.
- `SENTRY_DSN=...` turns on error reporting (no personal data is sent). Sentry's hosted service may be unreachable from Iran:
  use a self-hosted Sentry/GlitchTip DSN instead.
