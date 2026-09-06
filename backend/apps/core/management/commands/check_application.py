import time

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from rest_framework.test import APIClient


class Command(BaseCommand):
    help = "Read-only checks of application endpoints against the current database."

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(is_superuser=True, is_active=True).first()
        if user is None:
            raise CommandError("No active administrator for endpoint checks")
        client = APIClient()
        client.force_authenticate(user)
        paths = [
            "auth/me/", "departments/", "roles/", "users/", "business-groups/",
            "tags/", "business-systems/", "monitors/", "monitor-results/",
            "monitor-results/summary/", "business-chains/", "incidents/",
            "alert-rules/", "notification-channels/", "notification-logs/",
            "maintenance-windows/", "status-pages/", "audit-logs/", "login-records/",
            "dashboard/summary/", "reports/sla/", "system/settings/", "system/overview/",
            "public/branding/",
        ]
        failed = []
        for path in paths:
            started = time.monotonic()
            response = client.get(f"/api/v1/{path}", HTTP_HOST="localhost")
            elapsed = round((time.monotonic() - started) * 1000)
            self.stdout.write(f"{path}: HTTP {response.status_code}, {elapsed} ms")
            if response.status_code != 200:
                failed.append(path)
        if failed:
            raise CommandError(f"Failed endpoints: {', '.join(failed)}")
        self.stdout.write(self.style.SUCCESS(f"All {len(paths)} endpoints passed"))
