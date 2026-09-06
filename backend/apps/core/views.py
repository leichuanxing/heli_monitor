from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from redis import Redis


def live(_request):
    return JsonResponse({"status": "ok", "service": "backend"})


def ready(_request):
    checks = {}
    try:
        connection.ensure_connection()
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
    try:
        Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2).ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"
    status = 200 if all(value == "ok" for value in checks.values()) else 503
    return JsonResponse(
        {"status": "ok" if status == 200 else "error", "checks": checks}, status=status
    )
