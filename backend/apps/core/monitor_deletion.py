"""Permanently remove one monitor and its dependent operational data."""

from django.db import transaction

from apps.incidents.models import Incident
from apps.monitors.models import ChainNode, Monitor, StateTransition


@transaction.atomic
def delete_monitor(monitor_id):
    monitor = Monitor.objects.select_for_update().filter(pk=monitor_id).first()
    if monitor is None:
        return 0
    # Explicitly remove protected dependents before cascading probe results.
    Incident.objects.filter(monitor=monitor).delete()
    ChainNode.objects.filter(monitor=monitor).delete()
    StateTransition.objects.filter(monitor=monitor).delete()
    count, _ = monitor.delete()
    return count
