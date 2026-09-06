from datetime import timedelta

import pytest
from django.utils import timezone

from apps.businesses.models import BusinessSystem
from apps.core.state_engine import apply_result
from apps.incidents.models import Incident
from apps.monitors.models import Monitor, MonitorResult


@pytest.mark.django_db
def test_failure_and_recovery_thresholds():
    business = BusinessSystem.objects.create(code="TEST", name="测试业务")
    monitor = Monitor.objects.create(
        business=business,
        name="首页",
        monitor_type="HTTP",
        target="http://example.invalid",
        interval_seconds=60,
        timeout_seconds=5,
        failure_threshold=3,
        recovery_threshold=2,
    )

    def result(ok, n):
        now = timezone.now() + timedelta(seconds=n)
        return MonitorResult.objects.create(
            monitor=monitor,
            execution_key=str(n),
            scheduled_at=now,
            started_at=now,
            checked_at=now,
            finished_at=now,
            success=ok,
            error_type=None if ok else "CONNECT_TIMEOUT",
        )

    assert apply_result(result(False, 1)).status == "DEGRADED"
    assert apply_result(result(False, 2)).status == "DEGRADED"
    assert apply_result(result(False, 3)).status == "DOWN"
    assert Incident.objects.count() == 1
    assert apply_result(result(False, 4)).status == "DOWN"
    assert Incident.objects.count() == 1
    assert apply_result(result(True, 5)).status == "DOWN"
    assert apply_result(result(True, 6)).status == "UP"
    assert Incident.objects.get().status == "RECOVERED"
