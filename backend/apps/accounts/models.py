import uuid

from django.conf import settings
from django.db import models


class Department(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=64, unique=True)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["parent", "name"], name="uniq_department_sibling")
        ]


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL)
    phone = models.CharField(max_length=32, blank=True)
    data_scope = models.CharField(
        max_length=20,
        choices=[("ALL", "全部"), ("DEPARTMENT", "本部门"), ("SELF", "本人")],
        default="SELF",
    )


class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80, unique=True)
    code = models.CharField(max_length=64, unique=True)
    description = models.TextField(blank=True)
    permissions = models.JSONField(default=list)
    data_scope = models.CharField(
        max_length=20,
        choices=[("ALL", "全部"), ("DEPARTMENT", "本部门"), ("SELF", "本人")],
        default="SELF",
    )
    is_enabled = models.BooleanField(default=True)
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="business_roles", blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
