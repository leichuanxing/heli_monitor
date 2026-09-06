import uuid

from django.db import models

from apps.businesses.models import BusinessSystem
from apps.monitors.models import Monitor


class MaintenanceWindow(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    timezone = models.CharField(max_length=64, default="Asia/Shanghai")
    recurrence = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)
    continue_probing = models.BooleanField(default=True)
    suppress_notifications = models.BooleanField(default=True)
    exclude_from_sla = models.BooleanField(default=True)
    businesses = models.ManyToManyField(BusinessSystem, blank=True)
    monitors = models.ManyToManyField(Monitor, blank=True)
    is_enabled = models.BooleanField(default=True)
