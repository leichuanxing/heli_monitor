#!/bin/sh
set -eu

case "${1:-web}" in
  web)
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
    exec gunicorn config.asgi:application -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --workers 2 --access-logfile - --error-logfile -
    ;;
  worker)
    exec celery -A config worker --loglevel=INFO --concurrency="${CELERY_CONCURRENCY:-4}"
    ;;
  beat)
    exec celery -A config beat --loglevel=INFO --schedule=/tmp/celerybeat-schedule
    ;;
  *) exec "$@" ;;
esac

