from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone

from apps.incidents.models import Incident, IncidentTimeline
from apps.maintenance.models import MaintenanceWindow
from apps.monitors.models import MonitorState, StateTransition

from .alerting import queue_incident_notifications

OPEN = ("NEW", "ACKNOWLEDGED", "PROCESSING")


def in_maintenance(monitor, at=None):
    at = at or timezone.now()
    return (
        MaintenanceWindow.objects.filter(is_enabled=True, start_at__lte=at, end_at__gte=at)
        .filter(models_q(monitor))
        .exists()
    )


def models_q(monitor):
    from django.db.models import Q

    return Q(monitors=monitor) | Q(businesses=monitor.business)


@transaction.atomic
def apply_result(result):
    monitor = result.monitor
    state, _ = MonitorState.objects.select_for_update().get_or_create(monitor=monitor)
    previous = state.status
    if not monitor.is_enabled:
        new_status = "PAUSED"
    elif in_maintenance(monitor, result.checked_at):
        new_status = "MAINTENANCE"
    elif result.success:
        state.consecutive_successes += 1
        state.consecutive_failures = 0
        if (
            previous in ("DOWN", "DEGRADED", "UNKNOWN")
            and state.consecutive_successes < monitor.recovery_threshold
        ):
            new_status = previous
        else:
            new_status = (
                "DEGRADED"
                if monitor.warning_latency_ms
                and result.latency_ms
                and result.latency_ms >= monitor.warning_latency_ms
                else "UP"
            )
    else:
        state.consecutive_failures += 1
        state.consecutive_successes = 0
        new_status = (
            "DOWN" if state.consecutive_failures >= monitor.failure_threshold else "DEGRADED"
        )
    state.status = new_status
    state.last_result = result
    state.version += 1
    if new_status != previous:
        state.changed_at = result.checked_at
        StateTransition.objects.create(
            monitor=monitor,
            from_status=previous,
            to_status=new_status,
            occurred_at=result.checked_at,
            result=result,
        )
        if result.success and new_status == "UP" and previous in ("DOWN", "DEGRADED"):
            for incident in Incident.objects.filter(monitor=monitor, status__in=OPEN):
                incident.status = "RECOVERED"
                incident.recovered_at = result.checked_at
                incident.save(update_fields=["status", "recovered_at"])
                IncidentTimeline.objects.create(
                    incident=incident, action="RECOVERED", payload={"result_id": result.id}
                )
                queue_incident_notifications(incident, "RECOVERY")
    # 即使任务此前已因高延迟处于 DEGRADED，首次真实失败也必须立即产生事件。
    if not result.success and new_status in ("DEGRADED", "DOWN"):
        number = f"INC-{result.checked_at:%Y%m%d}-{str(monitor.id)[:8]}-{result.id}"
        incident, created = Incident.objects.get_or_create(
            monitor=monitor,
            status__in=OPEN,
            defaults={
                "number": number,
                "title": f"{monitor.name} 不可用",
                "summary": result.error_summary or "探测失败",
            },
        )
        if created:
            IncidentTimeline.objects.create(
                incident=incident,
                action="OPENED",
                payload={"result_id": result.id, "error_type": result.error_type},
            )
            queue_incident_notifications(incident, "OPEN")
    state.save()
    payload = {
        "type": "monitor.result",
        "monitor_id": str(monitor.id),
        "monitor_name": monitor.name,
        "business_id": str(monitor.business_id),
        "from_status": previous,
        "status": new_status,
        "status_changed": new_status != previous,
        "checked_at": result.checked_at.isoformat(),
        "latency_ms": result.latency_ms,
        "success": result.success,
    }
    transaction.on_commit(
        lambda: async_to_sync(get_channel_layer().group_send)(
            "monitor-status", {"type": "status_update", "payload": payload}
        )
    )
    return state
