"""Read-only server facts and path-safe file helpers behind the admin "server" panel.

Nothing here shells out or touches paths that were not listed first: every file the
panel serves or deletes must resolve inside one of the roots below.
"""
import os
import re
import shutil
from pathlib import Path

from django.conf import settings
from django.db import connection

BACKUP_NAME = re.compile(r'^(db|media)-\d{8}-\d{6}\.(sqlite3\.gz|dump|tar\.gz)$')
LOG_NAME = re.compile(r'^[\w.-]+\.log(\.\d+)?$')
TAIL_BYTES = 200_000


def media_roots():
    return {'media': Path(settings.MEDIA_ROOT), 'private': Path(settings.PRIVATE_MEDIA_ROOT)}


def logs_dir():
    return Path(settings.BASE_DIR) / 'logs'


def dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def _read_first_line(path):
    try:
        with open(path) as handle:
            return handle.readline()
    except OSError:
        return ''


def resources():
    """CPU load, RAM, disk and uptime from /proc; fields are None where the OS has no /proc."""
    info = {'cpus': os.cpu_count() or 1, 'load': None, 'mem_total': None, 'mem_used': None,
            'mem_percent': None, 'uptime_days': None}
    load = _read_first_line('/proc/loadavg').split()
    if len(load) >= 3:
        loads = tuple(float(x) for x in load[:3])
        info['load'] = loads
        info['load_percent'] = min(100, round(loads[0] / info['cpus'] * 100))
    try:
        with open('/proc/meminfo') as handle:
            mem = {k: int(v.split()[0]) * 1024 for k, v in (line.split(':', 1) for line in handle)}
        info['mem_total'] = mem['MemTotal']
        info['mem_used'] = mem['MemTotal'] - mem['MemAvailable']
        info['mem_percent'] = round(info['mem_used'] / info['mem_total'] * 100)
    except (OSError, KeyError, ValueError):
        pass
    up = _read_first_line('/proc/uptime').split()
    if up:
        info['uptime_days'] = round(float(up[0]) / 86400, 1)
    info['net_rx'], info['net_tx'] = network_totals()
    disk = shutil.disk_usage(settings.BASE_DIR)
    info.update(disk_total=disk.total, disk_used=disk.used, disk_percent=round(disk.used / disk.total * 100))
    info['warnings'] = [label for label, value in
                        (('CPU', info.get('load_percent')), ('RAM', info['mem_percent']), ('دیسک', info['disk_percent']))
                        if value is not None and value >= 85]
    return info


def folder_usage():
    rows = [('فایل‌های بارگذاری‌شده', Path(settings.MEDIA_ROOT)),
            ('فایل‌های خصوصی', Path(settings.PRIVATE_MEDIA_ROOT)),
            ('نسخه‌های پشتیبان', Path(settings.BACKUP_DIR)),
            ('گزارش‌ها (لاگ)', logs_dir())]
    return [(label, dir_size(path) if path.is_dir() else 0) for label, path in rows]


def database_size():
    db = settings.DATABASES['default']
    if db['ENGINE'].endswith('sqlite3'):
        try:
            return os.path.getsize(db['NAME'])
        except OSError:
            return None
    return None


def list_backups():
    directory = Path(settings.BACKUP_DIR)
    if not directory.is_dir():
        return []
    rows = [p for p in directory.iterdir() if p.is_file() and BACKUP_NAME.match(p.name)]
    return [{'name': p.name, 'size': p.stat().st_size, 'mtime': p.stat().st_mtime}
            for p in sorted(rows, key=lambda p: p.name, reverse=True)]


def backup_path(name):
    """Path of a listed backup, or None. The regex plus the directory check rule out traversal."""
    if not BACKUP_NAME.match(name or ''):
        return None
    path = Path(settings.BACKUP_DIR) / name
    return path if path.is_file() else None


def list_logs():
    directory = logs_dir()
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.iterdir() if p.is_file() and LOG_NAME.match(p.name))


def tail_log(name, lines=300):
    if name not in list_logs():
        return None
    path = logs_dir() / name
    with open(path, 'rb') as handle:
        handle.seek(0, os.SEEK_END)
        handle.seek(max(0, handle.tell() - TAIL_BYTES))
        data = handle.read().decode('utf-8', 'replace')
    return '\n'.join(data.splitlines()[-lines:])


def resolve_media(root_key, rel=''):
    """Resolve ``rel`` inside the chosen media root, or None if it escapes it or the root is unknown."""
    root = media_roots().get(root_key)
    if root is None:
        return None, None
    root = root.resolve()
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        return root, None
    return root, target


def list_media(directory):
    rows = []
    for entry in sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if entry.is_symlink():
            continue
        rows.append({'name': entry.name, 'is_dir': entry.is_dir(),
                     'size': dir_size(entry) if entry.is_dir() else entry.stat().st_size})
    return rows


def network_totals():
    """Bytes received / sent on all non-loopback interfaces since boot, or (None, None)."""
    rx = tx = 0
    try:
        with open('/proc/net/dev') as handle:
            for line in handle.readlines()[2:]:
                name, data = line.split(':', 1)
                if name.strip() == 'lo':
                    continue
                fields = data.split()
                rx, tx = rx + int(fields[0]), tx + int(fields[8])
    except (OSError, ValueError, IndexError):
        return None, None
    return rx, tx


def last_backup_age_hours():
    """Hours since the newest database backup, or None when there is none."""
    import time
    db_backups = [b for b in list_backups() if b['name'].startswith('db-')]
    if not db_backups:
        return None
    return round((time.time() - max(b['mtime'] for b in db_backups)) / 3600, 1)


def database_overview():
    """Engine, size and per-table row counts (largest first)."""
    tables = []
    with connection.cursor() as cursor:
        for name in connection.introspection.table_names(cursor):
            cursor.execute(f'SELECT COUNT(*) FROM {connection.ops.quote_name(name)}')   # names come from the schema
            tables.append((name, cursor.fetchone()[0]))
    tables.sort(key=lambda row: row[1], reverse=True)
    return {'vendor': connection.vendor, 'size': database_size(), 'tables': tables,
            'total_rows': sum(count for _, count in tables)}


def database_maintain(action):
    """``check``: integrity check (SQLite) / connectivity; ``optimize``: refresh planner stats and compact."""
    with connection.cursor() as cursor:
        if action == 'check':
            if connection.vendor == 'sqlite':
                cursor.execute('PRAGMA integrity_check')
                return cursor.fetchone()[0]
            cursor.execute('SELECT 1')
            return 'ok'
        cursor.execute('ANALYZE')
        if connection.vendor == 'sqlite':
            cursor.execute('PRAGMA optimize')
        return 'done'


def search_media(root, directory, query, limit=200):
    """Files under ``directory`` whose name contains ``query`` (case-insensitive), paths relative to ``root``."""
    query, rows = query.lower(), []
    for base, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(base, d))]
        for name in files:
            path = Path(base) / name
            if query in name.lower() and not path.is_symlink():
                rows.append({'name': path.relative_to(directory).as_posix(), 'is_dir': False, 'size': path.stat().st_size})
                if len(rows) >= limit:
                    return rows
    return rows
