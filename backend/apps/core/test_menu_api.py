from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Department, Role
from apps.alerts.models import AlertRule, NotificationChannel, NotificationLog
from apps.businesses.models import BusinessSystem
from apps.core.models import SystemSetting
from apps.core.tasks import cleanup_monitor_results, reconcile_incident_notifications
from apps.incidents.models import Incident
from apps.maintenance.models import MaintenanceWindow
from apps.monitors.models import Monitor, MonitorResult, MonitorState
from apps.status_pages.models import StatusPage


@pytest.fixture
def api():
    user = User.objects.create_superuser("menu-admin", password="StrongMenuPassword!1")
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.mark.django_db
def test_every_menu_endpoint_is_available(api):
    endpoints = [
        "departments",
        "roles",
        "users",
        "business-groups",
        "tags",
        "business-systems",
        "monitors",
        "monitor-results",
        "business-chains",
        "incidents",
        "alert-rules",
        "notification-channels",
        "notification-logs",
        "maintenance-windows",
        "status-pages",
        "audit-logs",
    ]
    for endpoint in endpoints:
        assert api.get(f"/api/v1/{endpoint}/").status_code == 200, endpoint
    assert api.get("/api/v1/dashboard/summary/").status_code == 200
    assert api.get("/api/v1/reports/sla/").status_code == 200
    assert api.get("/health/ready").status_code == 200
    assert api.get("/admin/").status_code == 404


@pytest.mark.django_db
def test_role_permissions_and_user_organization_are_enforced(api):
    department = Department.objects.create(name="技术部", code="TECH")
    role = Role.objects.create(name="监控只读", code="MONITOR_VIEWER", permissions=["monitor.view"])
    created = api.post(
        "/api/v1/users/",
        {
            "username": "viewer1",
            "password": "View3r!1",
            "department": str(department.id),
            "phone": "13800000000",
            "data_scope": "DEPARTMENT",
            "roles": [str(role.id)],
            "is_active": True,
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.data["department_name"] == "技术部"
    viewer = User.objects.get(username="viewer1")
    client = APIClient()
    client.force_authenticate(viewer)
    assert client.get("/api/v1/monitors/").status_code == 200
    assert client.post("/api/v1/monitors/", {}, format="json").status_code == 403
    assert client.get("/api/v1/users/").status_code == 403
    me = client.get("/api/v1/auth/me/")
    assert me.status_code == 200
    assert me.data["permissions"] == ["monitor.view"]


@pytest.mark.django_db
def test_crud_forms_and_key_actions(api):
    department = api.post("/api/v1/departments/", {"name": "测试部门", "code": "QA"}, format="json")
    assert department.status_code == 201
    tag = api.post("/api/v1/tags/", {"name": "核心", "color": "#ff0000"}, format="json")
    assert tag.status_code == 201
    business = api.post(
        "/api/v1/business-systems/",
        {"name": "测试业务", "code": "QA-BIZ", "department": department.data["id"]},
        format="json",
    )
    assert business.status_code == 201
    monitor = api.post(
        "/api/v1/monitors/",
        {
            "business": business.data["id"],
            "name": "存活探测",
            "monitor_type": "HTTP",
            "target": "http://192.168.31.61/health/live",
            "interval_seconds": 60,
            "timeout_seconds": 10,
            "tags": [tag.data["id"]],
        },
        format="json",
    )
    assert monitor.status_code == 201
    with patch(
        "apps.core.tasks.execute_probe", return_value={"success": True, "status_code": 200}
    ):
        assert api.post(f"/api/v1/monitors/{monitor.data['id']}/test/").data["success"]
        report = api.post("/api/v1/monitors/test-all/").data
        assert report["total"] == report["passed"] == 1
    assert MonitorResult.objects.filter(monitor_id=monitor.data["id"]).count() == 2
    assert MonitorState.objects.get(monitor_id=monitor.data["id"]).status == "UP"
    assert api.patch(f"/api/v1/tags/{tag.data['id']}/", {"name": "核心系统"}).status_code == 200
    assert api.delete(f"/api/v1/tags/{tag.data['id']}/").status_code == 204


@pytest.mark.django_db
def test_monitor_delete_archives_and_preserves_history(api):
    business = BusinessSystem.objects.create(name="删除测试业务", code="DELETE-BIZ")
    monitor = Monitor.objects.create(
        business=business,
        name="待删除探测",
        monitor_type="HTTP",
        target="http://example.com/health",
    )
    incident = Incident.objects.create(
        number="INC-DELETE-1", monitor=monitor, title="历史故障", severity="HIGH"
    )
    now = timezone.now()
    result = MonitorResult.objects.create(
        monitor=monitor,
        execution_key="delete-history-result",
        scheduled_at=now,
        started_at=now,
        checked_at=now,
        finished_at=now,
        success=False,
    )
    response = api.delete(f"/api/v1/monitors/{monitor.id}/")
    assert response.status_code == 204
    monitor.refresh_from_db()
    assert monitor.is_archived is True
    assert monitor.is_enabled is False
    assert Incident.objects.filter(pk=incident.pk, monitor=monitor).exists()
    incident.refresh_from_db()
    assert incident.status == "CLOSED"
    assert incident.resolution == "探测任务已删除，事件自动关闭"
    listed = api.get("/api/v1/monitors/").data["results"]
    assert not any(str(item["id"]) == str(monitor.id) for item in listed)
    result_ids = [item["id"] for item in api.get("/api/v1/monitor-results/").data["results"]]
    assert result.id not in result_ids
    dashboard = api.get("/api/v1/dashboard/summary/").data
    assert dashboard["monitors_total"] == 0
    assert dashboard["open_incidents"] == 0


@pytest.mark.django_db
def test_real_notification_test_result_and_bulk_summary(api):
    channel = NotificationChannel.objects.create(
        name="测试 Webhook", channel_type="WEBHOOK", config={"url": "https://example.com/hook"}
    )
    success = {"success": True, "message": "测试消息发送成功", "latency_ms": 12.3, "detail": {}}
    with patch("apps.core.api.send_test_notification", return_value=success):
        assert api.post(f"/api/v1/notification-channels/{channel.id}/test/").data["success"]
        report = api.post("/api/v1/notification-channels/test-all/").data
    assert report["total"] == report["passed"] == 1


@pytest.mark.django_db
def test_user_password_incident_and_readonly_guards(api):
    created = api.post(
        "/api/v1/users/",
        {"username": "operator1", "password": "Op3r!123", "is_active": True},
        format="json",
    )
    assert created.status_code == 201
    assert User.objects.get(username="operator1").check_password("Op3r!123")
    too_short = api.post(
        "/api/v1/users/",
        {"username": "operator2", "password": "1234567", "is_active": True},
        format="json",
    )
    assert too_short.status_code == 400
    long_password = "LongPassword!123"
    allowed = api.post(
        "/api/v1/users/",
        {"username": "operator3", "password": long_password, "is_active": True},
        format="json",
    )
    assert allowed.status_code == 201
    assert User.objects.get(username="operator3").check_password(long_password)
    business = BusinessSystem.objects.create(name="事件业务", code="INC-BIZ")
    monitor = Monitor.objects.create(
        business=business, name="事件探测", monitor_type="HTTP", target="http://example.com"
    )
    incident = Incident.objects.create(
        number="INC-TEST-1", monitor=monitor, title="测试事件", severity="HIGH"
    )
    assert (
        api.post(f"/api/v1/incidents/{incident.id}/acknowledge/").data["status"] == "ACKNOWLEDGED"
    )
    assert (
        api.post(f"/api/v1/incidents/{incident.id}/close/", {"resolution": "已恢复"}).data["status"]
        == "CLOSED"
    )
    now = timezone.now()
    result = MonitorResult.objects.create(
        monitor=monitor,
        execution_key="readonly-test",
        scheduled_at=now,
        started_at=now,
        checked_at=now,
        finished_at=now + timedelta(milliseconds=1),
        success=True,
    )
    assert api.delete(f"/api/v1/monitor-results/{result.id}/").status_code == 405
    assert api.post("/api/v1/audit-logs/", {}, format="json").status_code == 405


@pytest.mark.django_db
def test_serverchan_channel_validation_masking_and_delivery(api):
    invalid = api.post(
        "/api/v1/notification-channels/",
        {"name": "Server酱缺少密钥", "channel_type": "SERVERCHAN", "config": {}},
        format="json",
    )
    assert invalid.status_code == 400

    created = api.post(
        "/api/v1/notification-channels/",
        {
            "name": "Server酱测试",
            "channel_type": "SERVERCHAN",
            "config": {
                "sendkey": "SCT000000000000000000000000000000T",
                "tags": "运维|告警",
                "short": "测试摘要",
                "channel": "9|66",
                "openid": "openid-a|openid-b",
                "noip": True,
                "timeout": 8,
            },
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.data["config"]["sendkey"] == "********"

    response = Mock()
    response.status_code = 200
    response.headers = {"content-type": "application/json"}
    response.json.return_value = {"code": 0, "data": {"pushid": "push-1"}}
    response.raise_for_status.return_value = None
    with patch("apps.core.notifications.httpx.post", return_value=response) as post:
        result = api.post(f"/api/v1/notification-channels/{created.data['id']}/test/")
    assert result.status_code == 200
    assert result.data["success"] is True
    assert result.data["detail"]["pushid"] == "push-1"
    request_url = post.call_args.args[0]
    request_data = post.call_args.kwargs["data"]
    assert request_url == ("https://sctapi.ftqq.com/SCT000000000000000000000000000000T.send")
    assert request_data["title"] == "[HELI MONITOR] 通知渠道测试"
    assert request_data["tags"] == "运维|告警"
    assert request_data["noip"] == "1"

    updated = api.patch(
        f"/api/v1/notification-channels/{created.data['id']}/",
        {"config": {"sendkey": "********", "timeout": 12}},
        format="json",
    )
    assert updated.status_code == 200
    channel = NotificationChannel.objects.get(id=created.data["id"])
    assert channel.config["sendkey"] == "SCT000000000000000000000000000000T"
    assert channel.config["timeout"] == 12


@pytest.mark.django_db
def test_incident_rule_and_notification_operations(api):
    business = BusinessSystem.objects.create(name="告警闭环业务", code="ALERT-OPS")
    monitor = Monitor.objects.create(
        business=business, name="闭环探测", monitor_type="HTTP", target="http://example.com"
    )
    incident = Incident.objects.create(
        number="INC-OPS-1", monitor=monitor, title="闭环事件", summary="业务不可用"
    )
    acknowledged = api.post(f"/api/v1/incidents/{incident.id}/acknowledge/")
    assert acknowledged.status_code == 200
    processing = api.post(
        f"/api/v1/incidents/{incident.id}/process/", {"comment": "运维接手"}, format="json"
    )
    assert processing.status_code == 200
    assert processing.data["status"] == "PROCESSING"
    assert processing.data["assignee_name"] == "menu-admin"
    assert len(processing.data["timeline"]) == 2
    assert api.post(f"/api/v1/incidents/{incident.id}/close/", {}).status_code == 400

    invalid_rule = api.post(
        "/api/v1/alert-rules/",
        {
            "name": "非法升级规则",
            "severity": "HIGH",
            "repeat_interval_minutes": 30,
            "escalation_minutes": 10,
        },
        format="json",
    )
    assert invalid_rule.status_code == 400
    rule = AlertRule.objects.create(name="有效规则")
    toggled = api.post(f"/api/v1/alert-rules/{rule.id}/toggle/", {"enabled": False}, format="json")
    assert toggled.status_code == 200
    assert toggled.data["is_enabled"] is False

    channel = NotificationChannel.objects.create(
        name="闭环 Webhook", channel_type="WEBHOOK", config={"url": "https://example.com"}
    )
    log = NotificationLog.objects.create(
        incident=incident, phase="OPEN", channel=channel, status="FAILED", error_summary="超时"
    )
    delivery = {"success": True, "message": "发送成功", "latency_ms": 8, "detail": {}}
    with patch("apps.core.api.send_notification", return_value=delivery):
        retried = api.post(f"/api/v1/notification-logs/{log.id}/retry/")
    assert retried.status_code == 200
    assert retried.data["status"] == "SENT"
    assert retried.data["attempts"] == 1
    assert retried.data["incident_number"] == "INC-OPS-1"
    assert retried.data["channel_name"] == "闭环 Webhook"


@pytest.mark.django_db(transaction=True)
def test_manual_probe_drives_incident_dashboard_and_notification_associations(api):
    business = BusinessSystem.objects.create(name="状态联动业务", code="STATE-LINK")
    monitor = Monitor.objects.create(
        business=business,
        name="状态联动探测",
        monitor_type="HTTP",
        target="http://example.com",
        failure_threshold=1,
        recovery_threshold=1,
    )
    channel = NotificationChannel.objects.create(
        name="状态联动渠道", channel_type="WEBHOOK", config={"url": "https://example.com"}
    )
    rule = AlertRule.objects.create(name="状态联动规则", severity="CRITICAL")
    rule.monitors.add(monitor)
    rule.channels.add(channel)
    failed = {"success": False, "error_type": "CONNECT", "error_summary": "拒绝连接"}
    with (
        patch("apps.core.tasks.execute_probe", return_value=failed),
        patch("apps.core.tasks.deliver_notification.delay"),
    ):
        response = api.post(f"/api/v1/monitors/{monitor.id}/test/")
    assert response.status_code == 200
    assert MonitorState.objects.get(monitor=monitor).status == "DOWN"
    incident = Incident.objects.get(monitor=monitor, status="NEW")
    assert incident.severity == "CRITICAL"
    assert NotificationLog.objects.filter(
        incident=incident, channel=channel, phase="OPEN", status="PENDING"
    ).exists()
    dashboard = api.get("/api/v1/dashboard/summary/").data
    item = next(row for row in dashboard["latest_monitors"] if row["id"] == str(monitor.id))
    assert item["status"] == "DOWN"
    assert item["available"] is False
    assert dashboard["open_incidents"] == 1

    with (
        patch("apps.core.tasks.execute_probe", return_value={"success": True}),
        patch("apps.core.tasks.deliver_notification.delay"),
    ):
        api.post(f"/api/v1/monitors/{monitor.id}/test/")
    incident.refresh_from_db()
    assert incident.status == "RECOVERED"
    assert NotificationLog.objects.filter(
        incident=incident, channel=channel, phase="RECOVERY", status="PENDING"
    ).exists()


@pytest.mark.django_db
def test_monitor_result_retention_keeps_newest_records_for_each_monitor():
    setting = SystemSetting.load()
    setting.monitor_result_retention_count = 3
    setting.save(update_fields=["monitor_result_retention_count"])
    business = BusinessSystem.objects.create(name="留存测试业务", code="RETENTION")
    monitors = [
        Monitor.objects.create(
            business=business,
            name="留存探测",
            monitor_type="HTTP",
            target="http://example.com",
        ),
        Monitor.objects.create(
            business=business,
            name="第二留存探测",
            monitor_type="TCP",
            target="example.com:443",
        ),
    ]
    now = timezone.now()
    for monitor_index, monitor in enumerate(monitors):
        for index in range(5):
            at = now + timedelta(seconds=index)
            MonitorResult.objects.create(
                monitor=monitor,
                execution_key=f"retention-{monitor_index}-{index}",
                scheduled_at=at,
                started_at=at,
                checked_at=at,
                finished_at=at,
                success=True,
            )
    assert cleanup_monitor_results() == 4
    for monitor_index, monitor in enumerate(monitors):
        assert list(
            monitor.results.order_by("checked_at").values_list("execution_key", flat=True)
        ) == [
            f"retention-{monitor_index}-2",
            f"retention-{monitor_index}-3",
            f"retention-{monitor_index}-4",
        ]


@pytest.mark.django_db(transaction=True)
def test_notification_reconcile_repairs_missed_open_incident(api):
    business = BusinessSystem.objects.create(name="补偿通知业务", code="RECONCILE")
    monitor = Monitor.objects.create(
        business=business, name="补偿通知探测", monitor_type="HTTP", target="http://example.com"
    )
    channel = NotificationChannel.objects.create(
        name="补偿通知渠道", channel_type="WEBHOOK", config={"url": "https://example.com"}
    )
    rule = AlertRule.objects.create(name="补偿通知规则", repeat_interval_minutes=1)
    rule.monitors.add(monitor)
    rule.channels.add(channel)
    incident = Incident.objects.create(number="INC-RECONCILE", monitor=monitor, title="遗漏事件")
    with patch("apps.core.tasks.deliver_notification.delay") as delay:
        assert reconcile_incident_notifications() == 1
    log = NotificationLog.objects.get(incident=incident, channel=channel, phase="OPEN")
    assert log.status == "PENDING"
    delay.assert_called_once_with(log.id)

    NotificationLog.objects.filter(pk=log.pk).update(
        created_at=timezone.now() - timedelta(minutes=2)
    )
    with patch("apps.core.tasks.deliver_notification.delay") as repeat_delay:
        assert reconcile_incident_notifications() == 2
    repeat = NotificationLog.objects.get(incident=incident, channel=channel, phase="REPEAT")
    repeat_delay.assert_any_call(log.id)
    repeat_delay.assert_any_call(repeat.id)


@pytest.mark.django_db(transaction=True)
def test_first_failed_probe_notifies_before_down_threshold(api):
    business = BusinessSystem.objects.create(name="即时告警业务", code="IMMEDIATE")
    monitor = Monitor.objects.create(
        business=business,
        name="即时告警探测",
        monitor_type="HTTP",
        target="http://example.com",
        failure_threshold=3,
        recovery_threshold=1,
    )
    channel = NotificationChannel.objects.create(
        name="即时告警渠道", channel_type="WEBHOOK", config={"url": "https://example.com"}
    )
    rule = AlertRule.objects.create(name="即时告警规则")
    rule.monitors.add(monitor)
    rule.channels.add(channel)
    failure = {"success": False, "error_type": "CONNECT", "error_summary": "连接失败"}
    with (
        patch("apps.core.tasks.execute_probe", return_value=failure),
        patch("apps.core.tasks.deliver_notification.delay") as delivery,
    ):
        api.post(f"/api/v1/monitors/{monitor.id}/test/")
    state = MonitorState.objects.get(monitor=monitor)
    assert state.status == "DEGRADED"
    incident = Incident.objects.get(monitor=monitor, status="NEW")
    log = NotificationLog.objects.get(incident=incident, channel=channel, phase="OPEN")
    delivery.assert_called_once_with(log.id)


@pytest.mark.django_db
def test_maintenance_scope_status_page_business_and_sla_exclusion(api):
    business = BusinessSystem.objects.create(name="报表业务", code="REPORT-BIZ", sla_target=99.9)
    monitor = Monitor.objects.create(
        business=business, name="报表探测", monitor_type="HTTP", target="http://example.com"
    )
    now = timezone.now()
    MonitorResult.objects.create(
        monitor=monitor,
        execution_key="sla-maintenance-result",
        scheduled_at=now,
        started_at=now,
        checked_at=now,
        finished_at=now,
        success=False,
    )
    window = MaintenanceWindow.objects.create(
        name="报表维护",
        start_at=now - timedelta(minutes=1),
        end_at=now + timedelta(minutes=1),
        exclude_from_sla=True,
    )
    window.businesses.add(business)
    report = api.get("/api/v1/reports/sla/?days=1")
    assert report.status_code == 200
    row = report.data["results"][0]
    assert row["samples"] == 0
    assert row["excluded_samples"] == 1

    page = StatusPage.objects.create(name="业务状态", slug="report-status")
    page.businesses.add(business)
    public = api.get("/api/v1/public/status/report-status/")
    assert public.status_code == 200
    assert public.data["summary"]["total"] == 1
    assert public.data["monitors"][0]["name"] == monitor.name

    invalid = api.post(
        "/api/v1/maintenance-windows/",
        {"name": "无范围维护", "start_at": now, "end_at": now + timedelta(hours=1)},
        format="json",
    )
    assert invalid.status_code == 400
