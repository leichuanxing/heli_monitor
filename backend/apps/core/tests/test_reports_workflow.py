import csv
import hashlib
import io
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.businesses.models import BusinessSystem
from apps.maintenance.models import MaintenanceWindow
from apps.monitors.models import Monitor, MonitorResult, MonitorState
from apps.status_pages.models import StatusPage


@pytest.fixture
def api(db):
    client = APIClient()
    client.force_authenticate(User.objects.create_superuser("report-admin"))
    return client


@pytest.fixture
def monitor(db):
    business = BusinessSystem.objects.create(name="=1+1", code="REPORT-REG")
    return Monitor.objects.create(
        business=business, name="@probe", monitor_type="PING", target="127.0.0.1"
    )


def sample(monitor, when, success, key, latency=0):
    return MonitorResult.objects.create(
        monitor=monitor,
        execution_key=key,
        scheduled_at=when,
        started_at=when,
        checked_at=when,
        finished_at=when,
        success=success,
        latency_ms=latency,
    )


@pytest.mark.parametrize("query", ["days=0", "days=366", "days=no", "business=not-a-uuid"])
def test_sla_rejects_invalid_parameters(api, query):
    assert api.get("/api/v1/reports/sla/?" + query).status_code == 400
    assert api.get("/api/v1/reports/sla/export.csv?" + query).status_code == 400


def test_sla_excludes_overlapping_maintenance_once_and_future_samples(api, monitor):
    now = timezone.now()
    sample(monitor, now - timedelta(minutes=1), False, "maintenance")
    sample(monitor, now - timedelta(hours=2), True, "included")
    sample(monitor, now + timedelta(days=1), False, "future")
    for index in range(2):
        window = MaintenanceWindow.objects.create(
            name=str(index), start_at=now - timedelta(minutes=3), end_at=now + timedelta(minutes=2)
        )
        window.monitors.add(monitor)
    response = api.get("/api/v1/reports/sla/?days=1")
    row = response.data["results"][0]
    assert (row["samples"], row["excluded_samples"], row["availability"]) == (1, 1, 100)
    assert response.data["summary"]["total_samples"] == 2
    export = api.get("/api/v1/reports/sla/export.csv?days=1").content
    assert export.count(b"\xef\xbb\xbf") == 1
    rows = list(csv.reader(io.StringIO(export.decode("utf-8-sig"))))
    assert rows[1][0] == "'=1+1"
    assert rows[1][1] == "'@probe"
    assert float(rows[1][-1]) == 0


def test_maintenance_filters_and_timezone_validation(api, monitor):
    now = timezone.now()
    for enabled in (False, True):
        window = MaintenanceWindow.objects.create(
            name=str(enabled),
            start_at=now - timedelta(hours=2),
            end_at=now - timedelta(hours=1),
            is_enabled=enabled,
        )
        window.monitors.add(monitor)
    assert api.get("/api/v1/maintenance-windows/?state=DISABLED").data["count"] == 1
    assert api.get("/api/v1/maintenance-windows/?state=ENDED").data["count"] == 1
    assert api.get("/api/v1/maintenance-windows/?state=invalid").status_code == 400
    response = api.post(
        "/api/v1/maintenance-windows/",
        {
            "name": "Invalid zone",
            "start_at": now,
            "end_at": now + timedelta(hours=1),
            "timezone": "Invalid/Zone",
            "monitors": [str(monitor.pk)],
        },
        format="json",
    )
    assert response.status_code == 400


def test_report_options_do_not_require_asset_or_monitor_permission(api, monitor):
    user = User.objects.create_user("report-reader")
    role = Role.objects.create(
        name="Report reader", code="REPORT-READER", permissions=["report.view"]
    )
    user.business_roles.add(role)
    api.force_authenticate(user)
    response = api.get("/api/v1/reports/options/")
    assert response.status_code == 200
    assert str(response.data["monitors"][0]["id"]) == str(monitor.pk)
    assert "config" not in response.data["monitors"][0]
    assert api.get("/api/v1/monitors/").status_code == 403
    assert api.post("/api/v1/maintenance-windows/", {}, format="json").status_code == 403


def test_public_status_empty_pending_paused_and_active_maintenance(api, monitor):
    page = StatusPage.objects.create(name="State page", slug="state-reg")
    page.monitors.add(monitor)
    url = "/api/v1/public/status/state-reg/"
    assert api.get(url).data["overall_status"] == "PENDING"
    monitor.business.is_enabled = False
    monitor.business.save(update_fields=["is_enabled"])
    assert api.get(url).data["overall_status"] == "PAUSED"
    monitor.business.is_enabled = True
    monitor.business.save(update_fields=["is_enabled"])
    now = timezone.now()
    window = MaintenanceWindow.objects.create(
        name="Current",
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=1),
        continue_probing=False,
    )
    window.monitors.add(monitor)
    assert api.get(url).data["overall_status"] == "MAINTENANCE"
    monitor.is_archived = True
    monitor.save(update_fields=["is_archived"])
    assert api.get(url).data["overall_status"] == "UNKNOWN"


def test_public_status_token_rotation_preview_and_expired_login(api, monitor):
    page = StatusPage.objects.create(name="Token page", slug="token-reg", access_mode="TOKEN")
    page.monitors.add(monitor)
    url = "/api/v1/public/status/token-reg/"
    assert api.get(url).status_code == 403
    first = api.post(f"/api/v1/status-pages/{page.pk}/rotate-token/").data["token"]
    page.refresh_from_db()
    assert page.token_hash == hashlib.sha256(first.encode()).hexdigest()
    assert "token_hash" not in api.get(f"/api/v1/status-pages/{page.pk}/").data
    assert api.get(f"/api/v1/status-pages/{page.pk}/preview/").status_code == 200
    second = api.post(f"/api/v1/status-pages/{page.pk}/rotate-token/").data["token"]
    public = APIClient()
    assert public.get(url, HTTP_X_STATUS_TOKEN=first).status_code == 403
    response = public.get(
        url, HTTP_X_STATUS_TOKEN=second, HTTP_AUTHORIZATION="Bearer expired-invalid"
    )
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    page.is_enabled = False
    page.save(update_fields=["is_enabled"])
    assert public.get(url, HTTP_X_STATUS_TOKEN=second).status_code == 404


def test_status_page_theme_validation_and_failed_result_state(api, monitor):
    response = api.post(
        "/api/v1/status-pages/",
        {
            "name": "Invalid theme",
            "slug": "theme-reg",
            "theme_color": "red;bad",
            "monitors": [str(monitor.pk)],
        },
        format="json",
    )
    assert response.status_code == 400
    result = sample(monitor, timezone.now(), False, "failed")
    MonitorState.objects.create(monitor=monitor, status="UP", last_result=result)
    page = StatusPage.objects.create(name="Failed state", slug="failed-reg")
    page.monitors.add(monitor)
    assert api.get("/api/v1/public/status/failed-reg/").data["overall_status"] == "DEGRADED"
