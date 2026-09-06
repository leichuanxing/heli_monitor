import uuid

from django.conf import settings
from django.db import models

from apps.accounts.models import Department


class BusinessGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    name = models.CharField(max_length=120)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["parent", "name"], name="uniq_business_group_sibling")
        ]


class Tag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=64, unique=True)
    color = models.CharField(max_length=16, default="#409EFF")


class BusinessSystem(models.Model):
    LEVELS = [("CORE", "核心"), ("IMPORTANT", "重要"), ("NORMAL", "一般")]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    group = models.ForeignKey(
        BusinessGroup, null=True, blank=True, on_delete=models.PROTECT, related_name="businesses"
    )
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_businesses",
    )
    level = models.CharField(max_length=20, choices=LEVELS, default="NORMAL")
    environment = models.CharField(max_length=32, default="production")
    sla_target = models.DecimalField(max_digits=6, decimal_places=3, default=99.9)
    service_schedule = models.JSONField(default=dict, blank=True)
    tags = models.ManyToManyField(Tag, blank=True)
    is_enabled = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
