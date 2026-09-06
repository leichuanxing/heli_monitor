import uuid

from django.db import models

from apps.incidents.models import Incident


class AlertRule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    severity = models.CharField(max_length=20, default="HIGH")
    repeat_interval_minutes = models.PositiveIntegerField(default=30)
    escalation_minutes = models.PositiveIntegerField(default=60)
    monitors = models.ManyToManyField("monitors.Monitor", related_name="alert_rules")
    channels = models.ManyToManyField("NotificationChannel", related_name="alert_rules")
    is_enabled = models.BooleanField(default=True)


class NotificationChannel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel_type = models.CharField(
        max_length=20,
        choices=[(x, x) for x in ("EMAIL", "WECHAT", "DINGTALK", "WEBHOOK", "SERVERCHAN")]
    )
    name = models.CharField(max_length=120)
    config = models.JSONField(default=dict)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["channel_type", "name"], name="uniq_channel_name")
        ]


class NotificationLog(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="notifications")
    phase = models.CharField(max_length=20)
    channel = models.ForeignKey(NotificationChannel, on_delete=models.PROTECT)
    recipient_key = models.CharField(max_length=255, default="default")
    status = models.CharField(max_length=20, default="PENDING")
    attempts = models.PositiveIntegerField(default=0)
    error_summary = models.CharField(max_length=500, blank=True)
    sent_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["incident", "phase", "channel", "recipient_key"],
                name="uniq_notification_phase",
            )
        ]
