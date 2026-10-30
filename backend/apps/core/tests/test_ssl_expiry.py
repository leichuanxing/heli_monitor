import ssl
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.businesses.models import BusinessSystem
from apps.core.monitor_config import validate_config
from apps.core.probes import ssl_probe
from apps.core.serializers import MonitorSerializer
from apps.core.state_engine import apply_result
from apps.incidents.models import Incident
from apps.monitors.models import Monitor, MonitorResult


@pytest.mark.parametrize(
    "seconds,warning", [(30 * 86400, True), (30 * 86400 + 1, False), (1, True)]
)
@pytest.mark.parametrize("action", ["warn", "notify", "fail"])
def test_exact_warning_boundary(seconds, warning, action):
    now = datetime(2026, 10, 29, tzinfo=UTC)
    expires = now + timedelta(seconds=seconds)
    with (
        patch("apps.core.probes.datetime") as clock,
        patch("apps.core.probes.validate_target"),
        patch("apps.core.probes.socket.create_connection"),
        patch("apps.core.probes.ssl.create_default_context") as context,
    ):
        clock.now.return_value = now
        clock.strptime.return_value = expires
        conn = context.return_value.wrap_socket.return_value.__enter__.return_value
        conn.getpeercert.return_value = {"notAfter": "unused"}
        output = ssl_probe("example.com", {"warn_days": 30, "expiry_action": action})
    assert output["metrics"]["warning"] is warning
    assert output["success"] is not (warning and action == "fail")
    assert output["detail"]["not_after"] == expires.isoformat()


def test_notify_configuration():
    assert validate_config("SSL", "example.com:443", {"expiry_action": "notify", "warn_days": 7})
    with pytest.raises(ValueError):
        validate_config("SSL", "example.com:443", {"expiry_action": "invalid"})


def test_invalid_certificate_remains_failure_without_invented_expiry():
    with (
        patch("apps.core.probes.validate_target"),
        patch("apps.core.probes.socket.create_connection", side_effect=ssl.SSLError("expired")),
    ):
        output = ssl_probe("example.com", {"expiry_action": "notify"})
    assert output["success"] is False
    assert output["error_type"] == "TLS_ERROR"
    assert output.get("ssl_days_remaining") is None


@pytest.fixture
def monitor(db):
    business = BusinessSystem.objects.create(code="ssl-expiry", name="SSL expiry")
    return Monitor.objects.create(
        business=business,
        name="Certificate",
        monitor_type="SSL",
        target="example.com:443",
        config={"expiry_action": "notify", "warn_days": 30},
        recovery_threshold=2,
    )


def record(monitor, warning=True, success=True):
    at = timezone.now()
    return MonitorResult.objects.create(
        monitor=monitor,
        execution_key=str(uuid4()),
        scheduled_at=at,
        started_at=at,
        checked_at=at,
        finished_at=at,
        success=success,
        ssl_days_remaining=7,
        metrics={"warning": warning},
        detail={"not_after": "2026-11-05T00:00:00+00:00"},
    )


@pytest.mark.django_db
def test_notice_deduplicates_and_recovers_after_renewal(monitor):
    with patch("apps.core.state_engine.queue_incident_notifications") as queue:
        first = record(monitor)
        assert apply_result(first).status == "DEGRADED"
        assert MonitorSerializer(monitor).data["service_available"] is True
        incident = Incident.objects.get(monitor=monitor)
        assert "证书即将到期" in incident.title
        assert "2026-11-05" in incident.summary
        apply_result(record(monitor))
        assert Incident.objects.filter(monitor=monitor).count() == 1
        assert queue.call_count == 1
        apply_result(record(monitor, warning=False))
        incident.refresh_from_db()
        assert incident.status == "NEW"
        apply_result(record(monitor, warning=False))
        incident.refresh_from_db()
        assert incident.status == "RECOVERED"
        assert queue.call_args.args[1] == "RECOVERY"


@pytest.mark.django_db
def test_page_only_warning_does_not_notify(monitor):
    monitor.config["expiry_action"] = "warn"
    monitor.save()
    with patch("apps.core.state_engine.queue_incident_notifications") as queue:
        apply_result(record(monitor))
        assert not Incident.objects.filter(monitor=monitor).exists()
        queue.assert_not_called()


@pytest.mark.django_db
def test_valid_near_expiry_certificate_exits_down_state(monitor):
    monitor.failure_threshold = 1
    monitor.save()
    with patch("apps.core.state_engine.queue_incident_notifications"):
        assert apply_result(record(monitor, warning=False, success=False)).status == "DOWN"
        assert apply_result(record(monitor)).status == "DEGRADED"


@pytest.mark.django_db
def test_notice_uses_existing_channel_outbox_and_deduplicates(monitor):
    from apps.alerts.models import AlertRule, NotificationChannel, NotificationLog

    channel = NotificationChannel.objects.create(
        name="isolated webhook",
        channel_type="WEBHOOK",
        config={"url": "http://127.0.0.1:19999/never-called"},
    )
    rule = AlertRule.objects.create(name="Certificate rule")
    rule.monitors.add(monitor)
    rule.channels.add(channel)
    apply_result(record(monitor))
    apply_result(record(monitor))
    assert NotificationLog.objects.filter(incident__monitor=monitor, phase="OPEN").count() == 1
    apply_result(record(monitor, warning=False))
    apply_result(record(monitor, warning=False))
    assert NotificationLog.objects.filter(incident__monitor=monitor, phase="RECOVERY").count() == 1


@pytest.mark.django_db
def test_certificate_api_returns_raw_expiry_and_unknown_without_result(monitor):
    assert MonitorSerializer(monitor).data["certificate"] is None
    apply_result(record(monitor))
    monitor = Monitor.objects.select_related("state__last_result").get(pk=monitor.pk)
    data = MonitorSerializer(monitor).data["certificate"]
    assert data["expires_at"] == "2026-11-05T00:00:00+00:00"
    assert data["days_remaining"] == 7
    assert data["warning"] is True
    assert data["stale"] is False
