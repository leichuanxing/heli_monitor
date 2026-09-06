from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.monitors.models import Monitor, MonitorResult, StateTransition

from .probes import execute_probe
from .state_engine import apply_result


def execute_and_record(monitor, *, scheduled_at=None, execution_key=None):
    """执行一次探测并持久化结果，所有执行入口必须走同一状态机。"""
    scheduled_at = scheduled_at or timezone.now()
    execution_key = execution_key or f"manual:{monitor.id}:{scheduled_at.isoformat()}"
    existing = MonitorResult.objects.filter(execution_key=execution_key).first()
    if existing:
        return existing
    started = timezone.now()
    payload = execute_probe(
        monitor.monitor_type,
        monitor.target,
        {**monitor.config, "timeout": monitor.timeout_seconds},
    )
    finished = timezone.now()
    result = MonitorResult.objects.create(
        monitor=monitor,
        execution_key=execution_key,
        scheduled_at=scheduled_at,
        started_at=started,
        checked_at=finished,
        finished_at=finished,
        success=payload["success"],
        latency_ms=payload.get("latency_ms"),
        status_code=payload.get("status_code"),
        packet_loss=payload.get("packet_loss"),
        ssl_days_remaining=payload.get("ssl_days_remaining"),
        error_type=payload.get("error_type"),
        error_summary=payload.get("error_summary"),
        metrics=payload.get("metrics", {}),
        assertions=payload.get("assertions", []),
        detail=payload.get("detail", {}),
    )
    apply_result(result)
    return result


@shared_task(ignore_result=True)
def scheduler_scan():
    now = timezone.now()
    claimed = []
    with transaction.atomic():
        monitors = list(
            Monitor.objects.select_for_update(skip_locked=True)
            .filter(is_enabled=True, is_archived=False, next_run_at__lte=now)
            .order_by("next_run_at")[:200]
        )
        for monitor in monitors:
            scheduled = monitor.next_run_at
            monitor.next_run_at = max(scheduled + timedelta(seconds=monitor.interval_seconds), now)
            monitor.save(update_fields=["next_run_at"])
            claimed.append((str(monitor.id), scheduled.isoformat()))
    for monitor_id, scheduled in claimed:
        execute_monitor.delay(monitor_id, scheduled)
    return len(claimed)


@shared_task(ignore_result=True)
def cleanup_monitor_results():
    """每个探测任务仅保留各自最新的结果，分批清理其状态迁移引用。"""
    from .models import SystemSetting

    limit = max(SystemSetting.load().monitor_result_retention_count, 1)
    deleted = 0
    monitor_ids = MonitorResult.objects.values_list("monitor_id", flat=True).distinct()
    for monitor_id in monitor_ids.iterator():
        excess_ids = list(
            MonitorResult.objects.filter(monitor_id=monitor_id)
            .order_by("-checked_at", "-id")
            .values_list("id", flat=True)[limit:]
        )
        for start in range(0, len(excess_ids), 1000):
            batch = excess_ids[start : start + 1000]
            with transaction.atomic():
                StateTransition.objects.filter(result_id__in=batch).delete()
                count, _ = MonitorResult.objects.filter(id__in=batch).delete()
                deleted += count
    return deleted


@shared_task(ignore_result=True)
def reconcile_incident_notifications():
    """补偿因进程重启或队列瞬时异常而遗漏的开放事件通知。"""
    from apps.incidents.models import Incident

    from .alerting import queue_incident_notifications, queue_repeat_notifications

    created = 0
    incidents = Incident.objects.select_related("monitor").filter(
        status__in=("NEW", "ACKNOWLEDGED", "PROCESSING")
    )
    for incident in incidents:
        created += queue_incident_notifications(incident, "OPEN")
        created += queue_repeat_notifications(incident)
    return created


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
    soft_time_limit=55,
    time_limit=60,
)
def execute_monitor(self, monitor_id, scheduled_at):
    monitor = Monitor.objects.get(pk=monitor_id)
    scheduled = timezone.datetime.fromisoformat(scheduled_at)
    execution_key = f"{monitor_id}:{scheduled.isoformat()}"
    if MonitorResult.objects.filter(execution_key=execution_key).exists():
        return "duplicate"
    result = execute_and_record(monitor, scheduled_at=scheduled, execution_key=execution_key)
    return result.id


@shared_task(ignore_result=True)
def deliver_notification(notification_log_id):
    from apps.alerts.models import NotificationLog

    from .notifications import send_notification

    log = NotificationLog.objects.select_related("incident", "channel").get(pk=notification_log_id)
    if log.status == "SENT" or not log.channel.is_enabled:
        return log.status
    log.status = "RETRYING"
    log.save(update_fields=["status"])
    incident = log.incident
    phase_label = {"OPEN": "故障", "REPEAT": "故障持续", "RECOVERY": "恢复"}.get(
        log.phase, log.phase
    )
    result = send_notification(
        log.channel,
        f"[{incident.severity}] {incident.title}（{phase_label}）",
        f"事件编号：{incident.number}\n{incident.summary}",
    )
    log.attempts += 1
    log.status = "SENT" if result["success"] else "FAILED"
    log.error_summary = "" if result["success"] else result["message"]
    log.sent_at = timezone.now() if result["success"] else None
    log.save(update_fields=["attempts", "status", "error_summary", "sent_at"])
    return log.status
