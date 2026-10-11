#!/bin/sh
# Prepare the database and static files, then hand over to the main command (gunicorn).
set -e
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec "$@"
