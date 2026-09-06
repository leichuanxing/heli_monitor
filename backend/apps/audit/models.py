from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80)
    resource_type = models.CharField(max_length=80)
    resource_id = models.CharField(max_length=128)
    request_id = models.CharField(max_length=128, blank=True)
    source_ip = models.GenericIPAddressField(null=True)
    result = models.CharField(max_length=20, default="SUCCESS")
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class LoginRecord(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    username = models.CharField(max_length=150, db_index=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    success = models.BooleanField(default=False, db_index=True)
    failure_reason = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
