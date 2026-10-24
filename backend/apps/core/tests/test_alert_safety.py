from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.alerts.models import AlertRule, NotificationChannel, NotificationLog
from apps.businesses.models import BusinessSystem
from apps.core.alerting import apply_enabled_rule
from apps.core.secrets import decrypt_secret
from apps.core.serializers import NotificationChannelSerializer
from apps.core.tasks import deliver_notification
from apps.incidents.models import Incident
from apps.monitors.models import Monitor


@pytest.fixture
def api(db):
    client = APIClient()
    client.force_authenticate(User.objects.create_superuser("alert-regression"))
    return client


@pytest.fixture
def incident(db):
    business = BusinessSystem.objects.create(name="Alert regression", code="ALERT-REG")
    monitor = Monitor.objects.create(
        business=business, name="Alert probe", monitor_type="PING", target="127.0.0.1"
    )
    return Incident.objects.create(monitor=monitor, number="INC-REG", title="Failure")


@pytest.mark.parametrize(
    "config",
    [
        [],
        "bad",
        {"url": "https://example.com", "timeout": "bad"},
        {"url": "https://example.com", "port": 70000},
        {"url": "https://example.com", "headers": {"X": "a\nb"}},
    ],
)
def test_invalid_channel_configuration_returns_400(api, config):
    response = api.post(
        "/api/v1/notification-channels/",
        {"name": "Invalid", "channel_type": "WEBHOOK", "config": config},
        format="json",
    )
    assert response.status_code == 400


def test_toggle_boolean_and_severity(api):
    rule = AlertRule.objects.create(name="Boolean rule")
    response = api.post(
        f"/api/v1/alert-rules/{rule.pk}/toggle/", {"enabled": "false"}, format="json"
    )
    assert response.status_code == 200
    rule.refresh_from_db()
    assert rule.is_enabled is False
    assert (
        api.patch(
            f"/api/v1/alert-rules/{rule.pk}/", {"severity": "UNKNOWN"}, format="json"
        ).status_code
        == 400
    )


def test_secret_encrypted_and_serialization_does_not_mutate(api):
    response = api.post(
        "/api/v1/notification-channels/",
        {"name": "Secret", "channel_type": "SERVERCHAN", "config": {"sendkey": "test-only-key"}},
        format="json",
    )
    assert response.status_code == 201
    channel = NotificationChannel.objects.get(pk=response.data["id"])
    assert channel.config["sendkey"].startswith("fernet:v1:")
    assert decrypt_secret(channel.config["sendkey"]) == "test-only-key"
    before = dict(channel.config)
    assert NotificationChannelSerializer(channel).data["config"]["sendkey"] == "********"
    assert channel.config == before
    response = api.patch(
        f"/api/v1/notification-channels/{channel.pk}/",
        {"config": {"sendkey": "********"}},
        format="json",
    )
    assert response.status_code == 200
    channel.refresh_from_db()
    assert decrypt_secret(channel.config["sendkey"]) == "test-only-key"


def test_duplicate_delivery_and_manual_retry_guard(api, incident):
    channel = NotificationChannel.objects.create(name="Webhook", channel_type="WEBHOOK")
    log = NotificationLog.objects.create(incident=incident, channel=channel, phase="OPEN")
    with patch(
        "apps.core.notifications.send_notification", return_value={"success": True, "message": "ok"}
    ) as sender:
        assert deliver_notification(str(log.pk)) == "SENT"
        assert deliver_notification(str(log.pk)) == "SENT"
        sender.assert_called_once()
    assert api.post(f"/api/v1/notification-logs/{log.pk}/retry/").status_code == 400
    assert api.delete(f"/api/v1/notification-channels/{channel.pk}/").status_code == 400


def test_missing_and_exhausted_delivery(incident):
    channel = NotificationChannel.objects.create(name="Webhook", channel_type="WEBHOOK")
    log = NotificationLog.objects.create(
        incident=incident, channel=channel, phase="OPEN", status="FAILED", attempts=3
    )
    with patch("apps.core.notifications.send_notification") as sender:
        assert deliver_notification(str(log.pk)) == "FAILED"
        log_id = str(log.pk)
        log.delete()
        assert deliver_notification(log_id) == "deleted"
        sender.assert_not_called()


def test_escalation_applies_to_ongoing_incidents(incident):
    rule = AlertRule.objects.create(name="Escalation", severity="MEDIUM", escalation_minutes=60)
    incident.opened_at = timezone.now() - timedelta(minutes=61)
    apply_enabled_rule(incident, [rule])
    assert incident.severity == "HIGH"
