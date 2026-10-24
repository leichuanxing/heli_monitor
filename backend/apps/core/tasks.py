from copy import deepcopy
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.monitors.models import Monitor, MonitorResult, StateTransition

from .probes import execute_probe
from .state_engine import active_maintenance, apply_result


def execute_and_record(monitor, *, scheduled_at=None, execution_key=None):
    """执行一次探测并持久化结果，所有执行入口必须走同一状态机。"""
    scheduled_at = scheduled_at or timezone.now()
    execution_key = execution_key or f"manual:{monitor.id}:{scheduled_at.isoformat()}"
    existing = MonitorResult.objects.filter(execution_key=execution_key).first()
    if existing:
        return existing
    snapshot = {
        "name": monitor.name,
        "monitor_type": monitor.monitor_type,
        "target": monitor.target,
        "business_id": str(monitor.business_id),
        "business_name": monitor.business.name,
    }
    probe_spec = (monitor.monitor_type, monitor.target, deepcopy(monitor.config))
    started = timezone.now()
    payload = execute_probe(
        monitor.monitor_type,
        monitor.target,
        {**monitor.config, "timeout": monitor.timeout_seconds},
    )
    finished = timezone.now()
    with transaction.atomic():
        monitor = (
            Monitor.objects.select_for_update()
            .select_related("business")
            .filter(pk=monitor.pk)
            .first()
        )
        if monitor is None:
            raise NotFound("探测任务已删除")
        existing = MonitorResult.objects.filter(execution_key=execution_key).first()
        if existing:
            return existing
        result = MonitorResult.objects.create(
            monitor=monitor,
            monitor_snapshot=snapshot,
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
        if probe_spec == (monitor.monitor_type, monitor.target, monitor.config):
            apply_result(result)
    return result


@shared_task(ignore_result=True)
def scheduler_scan():
    now = timezone.now()
    claimed = []
    with transaction.atomic():
        monitors = list(
            Monitor.objects.select_for_update(skip_locked=True)
            .filter(
                is_enabled=True,
                is_archived=False,
                next_run_at__lte=now,
                business__is_enabled=True,
                business__is_archived=False,
            )
            .order_by("next_run_at")[:200]
        )
        for monitor in monitors:
            paused_until = (
                active_maintenance(monitor, now)
                .filter(continue_probing=False)
                .order_by("-end_at")
                .values_list("end_at", flat=True)
                .first()
            )
            if paused_until:
                monitor.next_run_at = paused_until
                monitor.save(update_fields=["next_run_at"])
                continue
            scheduled = monitor.next_run_at
            monitor.next_run_at = max(scheduled + timedelta(seconds=monitor.interval_seconds), now)
            monitor.save(update_fields=["next_run_at"])
            execute_monitor.delay(str(monitor.id), scheduled.isoformat())
            claimed.append((str(monitor.id), scheduled.isoformat()))
    return len(claimed)


@shared_task(ignore_result=True)
def cleanup_monitor_results():
    """每个探测任务仅保留各自最新的结果，分批清理其状态迁移引用。"""
    from .models import SystemSetting

    limit = max(SystemSetting.load().monitor_result_retention_count, 1)
    deleted = 0
    monitor_ids = MonitorResult.objects.values_list("monitor_id", flat=True).distinct()
    for monitor_id in monitor_ids.iterator():
        protected_since = timezone.now() - timedelta(days=31)
        keep = (
            MonitorResult.objects.filter(monitor_id=monitor_id)
            .order_by("-checked_at", "-id")
            .values("pk")[:limit]
        )
        excess_ids = list(
            MonitorResult.objects.filter(monitor_id=monitor_id, checked_at__lt=protected_since)
            .exclude(pk__in=keep)
            .values_list("pk", flat=True)
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
    # Recovery events are no longer open, so repair their pending deliveries separately.
    recoveries = (
        Incident.objects.select_related("monitor")
        .filter(
            status="RECOVERED", notifications__phase="RECOVERY", notifications__status="PENDING"
        )
        .distinct()
    )
    for incident in recoveries:
        created += queue_incident_notifications(incident, "RECOVERY")
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
    monitor = Monitor.objects.select_related("business").filter(pk=monitor_id).first()
    if monitor is None:
        return "deleted"
    if (
        not monitor.is_enabled
        or monitor.is_archived
        or not monitor.business.is_enabled
        or monitor.business.is_archived
    ):
        return "disabled"
    if active_maintenance(monitor).filter(continue_probing=False).exists():
        return "maintenance"
    scheduled = timezone.datetime.fromisoformat(scheduled_at)
    execution_key = f"{monitor_id}:{scheduled.isoformat()}"
    if MonitorResult.objects.filter(execution_key=execution_key).exists():
        return "duplicate"
    try:
        result = execute_and_record(monitor, scheduled_at=scheduled, execution_key=execution_key)
    except NotFound:
        return "deleted"
    return result.id


@shared_task(bind=True, max_retries=2, ignore_result=True)
def deliver_notification(self, notification_log_id):
    from apps.alerts.models import NotificationLog

    from .notifications import send_notification

    with transaction.atomic():
        log = (
            NotificationLog.objects.select_for_update(of=("self",))
            .select_related("incident", "channel")
            .filter(pk=notification_log_id)
            .first()
        )
        if log is None:
            return "deleted"
        if log.attempts >= 3:
            return log.status
        if log.status == "SENT" or not log.channel.is_enabled:
            return log.status
        if log.phase in ("OPEN", "REPEAT") and log.incident.status not in (
            "NEW",
            "ACKNOWLEDGED",
            "PROCESSING",
        ):
            log.status = "FAILED"
            log.error_summary = "事件已恢复或关闭，已取消过期故障通知"
            log.save(update_fields=["status", "error_summary"])
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
    if not result["success"]:
        raise self.retry(countdown=30 * (2**self.request.retries))
    return log.status
