import uuid

from django.db import models

from apps.businesses.models import BusinessSystem
from apps.monitors.models import Monitor


class StatusPage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    access_mode = models.CharField(
        max_length=20, choices=[("PUBLIC", "公开"), ("TOKEN", "令牌")], default="PUBLIC"
    )
    token_hash = models.CharField(max_length=128, blank=True)
    theme_color = models.CharField(max_length=16, default="#0c6c79")
    businesses = models.ManyToManyField(BusinessSystem, blank=True)
    monitors = models.ManyToManyField(Monitor, blank=True)
    is_enabled = models.BooleanField(default=True)
