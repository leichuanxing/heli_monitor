from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.alerts.models import AlertRule, NotificationChannel, NotificationLog

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def matching_rules(incident):
    return list(
        AlertRule.objects.filter(is_enabled=True, monitors=incident.monitor)
        .prefetch_related("channels")
        .distinct()
    )


def apply_enabled_rule(incident, rules):
    if not rules:
        return False
    severity = min((rule.severity for rule in rules), key=SEVERITY_ORDER.get)
    if incident.severity != severity:
        incident.severity = severity
        incident.save(update_fields=["severity"])
    return True


def queue_incident_notifications(incident, phase):
    rules = matching_rules(incident)
    if not apply_enabled_rule(incident, rules):
        return 0
    created_ids = []
    channel_ids = {
        channel.id
        for rule in rules
        for channel in rule.channels.all()
        if channel.is_enabled
    }
    for channel in NotificationChannel.objects.filter(id__in=channel_ids, is_enabled=True):
        log, created = NotificationLog.objects.get_or_create(
            incident=incident,
            phase=phase,
            channel=channel,
            recipient_key="default",
        )
        if created or log.status == "PENDING":
            created_ids.append(log.id)
    if created_ids:
        from .tasks import deliver_notification

        transaction.on_commit(
            lambda ids=created_ids: [deliver_notification.delay(log_id) for log_id in ids]
        )
    return len(created_ids)


def queue_repeat_notifications(incident):
    """按每个渠道匹配规则中的最短间隔持续提醒，事件恢复后不再调用。"""
    rules = matching_rules(incident)
    if not rules:
        return 0
    intervals = {}
    for rule in rules:
        for channel in rule.channels.all():
            if channel.is_enabled:
                intervals[channel.id] = min(
                    intervals.get(channel.id, rule.repeat_interval_minutes),
                    rule.repeat_interval_minutes,
                )
    now = timezone.now()
    created_ids = []
    for channel_id, minutes in intervals.items():
        last = (
            NotificationLog.objects.filter(
                incident=incident, channel_id=channel_id, phase__in=("OPEN", "REPEAT")
            )
            .order_by("-created_at")
            .first()
        )
        if not last or now - last.created_at < timedelta(minutes=minutes):
            continue
        bucket = int(now.timestamp() // (minutes * 60))
        log, created = NotificationLog.objects.get_or_create(
            incident=incident,
            phase="REPEAT",
            channel_id=channel_id,
            recipient_key=f"repeat:{bucket}",
        )
        if created or log.status == "PENDING":
            created_ids.append(log.id)
    if created_ids:
        from .tasks import deliver_notification

        transaction.on_commit(
            lambda ids=created_ids: [deliver_notification.delay(log_id) for log_id in ids]
        )
    return len(created_ids)
