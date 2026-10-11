FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# libmagic: upload type detection; postgresql-client: pg_dump for backup_db; curl: container health check
RUN apt-get update \
 && apt-get install -y --no-install-recommends libmagic1 postgresql-client curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN useradd --create-home --uid 10001 app \
 && mkdir -p /app/media /app/logs /app/staticfiles /app/backups \
 && chown -R app:app /app
USER app

EXPOSE 8000
ENTRYPOINT ["sh", "/app/docker/entrypoint.sh"]
CMD ["gunicorn", "django_project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-"]
