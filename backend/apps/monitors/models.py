import uuid

from django.db import models
from django.utils import timezone

from apps.businesses.models import BusinessSystem, Tag

STATUS_CHOICES = [
    (x, x) for x in ("PENDING", "UP", "DEGRADED", "DOWN", "PAUSED", "MAINTENANCE", "UNKNOWN")
]
TYPE_CHOICES = [
    (x, x)
    for x in (
        "HTTP",
        "API",
        "TCP",
        "PING",
        "DNS",
        "SSL",
        "MSSQL",
        "POSTGRESQL",
        "MYSQL",
        "MONGODB",
    )
]


class Monitor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(BusinessSystem, on_delete=models.CASCADE, related_name="monitors")
    name = models.CharField(max_length=160)
    monitor_type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    target = models.CharField(max_length=2048)
    interval_seconds = models.PositiveIntegerField(default=60)
    timeout_seconds = models.PositiveIntegerField(default=10)
    failure_threshold = models.PositiveIntegerField(default=3)
    recovery_threshold = models.PositiveIntegerField(default=2)
    warning_latency_ms = models.PositiveIntegerField(null=True, blank=True)
    config = models.JSONField(default=dict, blank=True)
    tags = models.ManyToManyField(Tag, blank=True)
    is_enabled = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    next_run_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["is_enabled", "next_run_at"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(timeout_seconds__lt=models.F("interval_seconds")),
                name="timeout_lt_interval",
            )
        ]


class MonitorResult(models.Model):
    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="results")
    execution_key = models.CharField(max_length=128, unique=True)
    scheduled_at = models.DateTimeField()
    started_at = models.DateTimeField()
    checked_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField()
    success = models.BooleanField()
    latency_ms = models.FloatField(null=True)
    status_code = models.IntegerField(null=True)
    packet_loss = models.FloatField(null=True)
    ssl_days_remaining = models.IntegerField(null=True)
    error_type = models.CharField(max_length=40, null=True)
    error_summary = models.CharField(max_length=500, null=True)
    metrics = models.JSONField(default=dict)
    assertions = models.JSONField(default=list)
    detail = models.JSONField(default=dict)

    class Meta:
        indexes = [models.Index(fields=["monitor", "-checked_at"])]


class MonitorState(models.Model):
    monitor = models.OneToOneField(
        Monitor, primary_key=True, on_delete=models.CASCADE, related_name="state"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    consecutive_failures = models.PositiveIntegerField(default=0)
    consecutive_successes = models.PositiveIntegerField(default=0)
    changed_at = models.DateTimeField(default=timezone.now)
    last_result = models.ForeignKey(MonitorResult, null=True, on_delete=models.SET_NULL)
    version = models.PositiveIntegerField(default=0)


class StateTransition(models.Model):
    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="transitions")
    from_status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    to_status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    occurred_at = models.DateTimeField(default=timezone.now)
    result = models.ForeignKey(MonitorResult, on_delete=models.PROTECT)

    class Meta:
        indexes = [models.Index(fields=["monitor", "-occurred_at"])]


class BusinessChain(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(BusinessSystem, on_delete=models.CASCADE, related_name="chains")
    name = models.CharField(max_length=160)
    is_enabled = models.BooleanField(default=True)


class ChainNode(models.Model):
    chain = models.ForeignKey(BusinessChain, on_delete=models.CASCADE, related_name="nodes")
    monitor = models.ForeignKey(Monitor, on_delete=models.PROTECT)
    name = models.CharField(max_length=160)
    is_critical = models.BooleanField(default=True)
    position = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["chain", "monitor"], name="uniq_chain_monitor")
        ]


class ChainEdge(models.Model):
    chain = models.ForeignKey(BusinessChain, on_delete=models.CASCADE, related_name="edges")
    source = models.ForeignKey(ChainNode, on_delete=models.CASCADE, related_name="out_edges")
    target = models.ForeignKey(ChainNode, on_delete=models.CASCADE, related_name="in_edges")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["chain", "source", "target"], name="uniq_chain_edge")
        ]
