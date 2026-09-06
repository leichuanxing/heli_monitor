import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.monitors.models import Monitor


class Incident(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=32, unique=True)
    monitor = models.ForeignKey(Monitor, on_delete=models.PROTECT, related_name="incidents")
    status = models.CharField(
        max_length=20,
        choices=[(x, x) for x in ("NEW", "ACKNOWLEDGED", "PROCESSING", "RECOVERED", "CLOSED")],
        default="NEW",
    )
    severity = models.CharField(
        max_length=20,
        choices=[(x, x) for x in ("CRITICAL", "HIGH", "MEDIUM", "LOW")],
        default="HIGH",
    )
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True)
    opened_at = models.DateTimeField(default=timezone.now)
    acknowledged_at = models.DateTimeField(null=True)
    recovered_at = models.DateTimeField(null=True)
    closed_at = models.DateTimeField(null=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="assigned_incidents",
    )
    root_cause = models.TextField(blank=True)
    resolution = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "-opened_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["monitor"],
                condition=models.Q(status__in=["NEW", "ACKNOWLEDGED", "PROCESSING"]),
                name="uniq_open_incident",
            )
        ]


class IncidentTimeline(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="timeline")
    action = models.CharField(max_length=40)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    occurred_at = models.DateTimeField(default=timezone.now)
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ["occurred_at"]
