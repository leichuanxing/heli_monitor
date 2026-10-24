from datetime import timedelta
from unittest.mock import patch

import httpx
import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.businesses.models import BusinessSystem
from apps.core.probes import http_probe
from apps.core.state_engine import apply_result
from apps.core.tasks import execute_and_record, execute_monitor, scheduler_scan
from apps.monitors.models import Monitor, MonitorResult


@pytest.fixture
def monitor(db):
    business = BusinessSystem.objects.create(code="REGRESSION", name="Regression")
    return Monitor.objects.create(
        business=business,
        name="Regression",
        monitor_type="HTTP",
        target="https://example.com",
        timeout_seconds=5,
    )


@pytest.mark.django_db
def test_sla_export_contains_actual_report_and_rejects_invalid_days():
    user = User.objects.create_superuser("export-admin", password="TestPassword123!")
    client = APIClient()
    client.force_authenticate(user)
    response = client.get("/api/v1/reports/sla/export.csv")
    assert response.status_code == 200
    assert "text/csv" in response["Content-Type"]
    assert "实际可用率" in response.content.decode("utf-8-sig")
    assert client.get("/api/v1/reports/sla/export.csv?days=abc").status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["dashboard/summary/", "reports/sla/", "reports/sla/export.csv"])
def test_users_without_role_cannot_read_protected_reports(path):
    client = APIClient()
    client.force_authenticate(User.objects.create_user("no-role"))
    assert client.get("/api/v1/" + path).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("config", [[], ["bad"], "invalid", {"auth": "invalid"}])
def test_monitor_rejects_malformed_config(monitor, config):
    client = APIClient()
    client.force_authenticate(User.objects.create_superuser("config-admin"))
    response = client.patch(f"/api/v1/monitors/{monitor.pk}/", {"config": config}, format="json")
    assert response.status_code == 400


def test_redirect_to_blocked_target_is_not_requested():
    response = httpx.Response(
        302,
        headers={"location": "http://127.0.0.1/admin"},
        request=httpx.Request("GET", "https://example.com"),
    )

    def validate(url):
        if "127.0.0.1" in url:
            raise ValueError("blocked")

    with (
        patch("apps.core.probes._validated_url", side_effect=validate),
        patch("apps.core.probes.httpx.request", return_value=response) as request,
    ):
        result = http_probe("https://example.com", {})
    assert not result["success"]
    assert request.call_count == 1


@pytest.mark.django_db
def test_result_is_rolled_back_when_state_application_fails(monitor):
    with (
        patch("apps.core.tasks.execute_probe", return_value={"success": True}),
        patch("apps.core.tasks.apply_result", side_effect=RuntimeError("state failure")),
        pytest.raises(RuntimeError),
    ):
        execute_and_record(monitor, execution_key="rollback")
    assert not MonitorResult.objects.filter(execution_key="rollback").exists()


@pytest.mark.django_db
def test_broker_failure_does_not_advance_schedule(monitor):
    due = monitor.next_run_at
    with (
        patch("apps.core.tasks.execute_monitor.delay", side_effect=RuntimeError("broker")),
        pytest.raises(RuntimeError),
    ):
        scheduler_scan()
    monitor.refresh_from_db()
    assert monitor.next_run_at == due


@pytest.mark.django_db
def test_disabled_queued_monitor_is_not_executed(monitor):
    monitor.is_enabled = False
    monitor.save()
    with patch("apps.core.tasks.execute_probe") as probe:
        assert execute_monitor(str(monitor.pk), timezone.now().isoformat()) == "disabled"
    probe.assert_not_called()


@pytest.mark.django_db
def test_old_result_cannot_replace_current_state(monitor):
    now = timezone.now()

    def result(key, at, success):
        return MonitorResult.objects.create(
            monitor=monitor,
            execution_key=key,
            scheduled_at=at,
            started_at=at,
            checked_at=at,
            finished_at=at,
            success=success,
        )

    latest = result("latest", now, True)
    apply_result(latest)
    state = apply_result(result("old", now - timedelta(minutes=1), False))
    assert state.status == "UP"
    assert state.last_result_id == latest.pk


@pytest.mark.django_db
def test_maintenance_pauses_automatic_probes(monitor):
    from apps.maintenance.models import MaintenanceWindow

    now = timezone.now()
    window = MaintenanceWindow.objects.create(
        name="Pause",
        start_at=now - timedelta(minutes=1),
        end_at=now + timedelta(minutes=1),
        continue_probing=False,
    )
    window.monitors.add(monitor)
    with patch("apps.core.tasks.execute_monitor.delay") as enqueue:
        assert scheduler_scan() == 0
    enqueue.assert_not_called()
    assert execute_monitor(str(monitor.pk), now.isoformat()) == "maintenance"


@pytest.mark.django_db
def test_maintenance_suppresses_existing_incident_reminders(monitor):
    from apps.alerts.models import AlertRule, NotificationChannel
    from apps.core.alerting import matching_rules
    from apps.incidents.models import Incident
    from apps.maintenance.models import MaintenanceWindow

    incident = Incident.objects.create(monitor=monitor, number="maintenance-test", title="Test")
    rule = AlertRule.objects.create(name="maintenance-test")
    rule.monitors.add(monitor)
    rule.channels.add(NotificationChannel.objects.create(name="test", channel_type="WEBHOOK"))
    assert len(matching_rules(incident)) == 1
    now = timezone.now()
    window = MaintenanceWindow.objects.create(
        name="Suppress",
        start_at=now - timedelta(minutes=1),
        end_at=now + timedelta(minutes=1),
        suppress_notifications=True,
    )
    window.businesses.add(monitor.business)
    assert matching_rules(incident) == []
    window.suppress_notifications = False
    window.save()
    assert len(matching_rules(incident)) == 1


@pytest.mark.django_db
def test_disabled_business_is_not_scheduled(monitor):
    monitor.business.is_enabled = False
    monitor.business.save()
    with patch("apps.core.tasks.execute_monitor.delay") as enqueue:
        assert scheduler_scan() == 0
    enqueue.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("suppress", [True, False])
def test_maintenance_respects_alert_setting_and_recovers(monitor, suppress):
    from apps.incidents.models import Incident
    from apps.maintenance.models import MaintenanceWindow

    now = timezone.now()
    window = MaintenanceWindow.objects.create(
        name="Event test",
        start_at=now - timedelta(minutes=1),
        end_at=now + timedelta(minutes=1),
        suppress_notifications=suppress,
    )
    window.monitors.add(monitor)
    for index, success in enumerate([False, True, True]):
        at = now + timedelta(seconds=index)
        result = MonitorResult.objects.create(
            monitor=monitor,
            execution_key=f"maint-{index}",
            scheduled_at=at,
            started_at=at,
            checked_at=at,
            finished_at=at,
            success=success,
        )
        state = apply_result(result)
        assert state.status == "MAINTENANCE"
        if index == 0:
            assert Incident.objects.filter(monitor=monitor).exists() is (not suppress)
    assert not Incident.objects.filter(
        monitor=monitor, status__in=["NEW", "ACKNOWLEDGED", "PROCESSING"]
    ).exists()


@pytest.mark.django_db
def test_notification_failure_is_recorded_and_retried(monitor):
    from celery.exceptions import Retry

    from apps.alerts.models import NotificationChannel, NotificationLog
    from apps.core.tasks import deliver_notification
    from apps.incidents.models import Incident

    incident = Incident.objects.create(monitor=monitor, number="retry-test", title="Retry")
    channel = NotificationChannel.objects.create(name="retry", channel_type="WEBHOOK")
    log = NotificationLog.objects.create(incident=incident, channel=channel, phase="OPEN")
    with (
        patch(
            "apps.core.notifications.send_notification",
            return_value={"success": False, "message": "temporary"},
        ),
        patch.object(deliver_notification, "retry", side_effect=Retry()) as retry,
        pytest.raises(Retry),
    ):
        deliver_notification(log.pk)
    log.refresh_from_db()
    assert log.status == "FAILED"
    assert log.attempts == 1
    retry.assert_called_once_with(countdown=30)


@pytest.mark.django_db
def test_reconcile_repairs_pending_recovery_delivery(monitor, django_capture_on_commit_callbacks):
    from apps.alerts.models import AlertRule, NotificationChannel, NotificationLog
    from apps.core.tasks import reconcile_incident_notifications
    from apps.incidents.models import Incident

    incident = Incident.objects.create(
        monitor=monitor, number="recovery-pending", title="Recovery", status="RECOVERED"
    )
    channel = NotificationChannel.objects.create(name="recovery", channel_type="WEBHOOK")
    rule = AlertRule.objects.create(name="recovery")
    rule.monitors.add(monitor)
    rule.channels.add(channel)
    log = NotificationLog.objects.create(incident=incident, channel=channel, phase="RECOVERY")
    with (
        patch("apps.core.tasks.deliver_notification.delay") as send,
        django_capture_on_commit_callbacks(execute=True),
    ):
        assert reconcile_incident_notifications() == 1
    send.assert_called_once_with(log.pk)
