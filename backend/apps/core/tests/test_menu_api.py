from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditLog, LoginRecord
from apps.businesses.models import BusinessSystem
from apps.incidents.models import Incident, IncidentTimeline
from apps.monitors.models import Monitor, MonitorResult


@pytest.fixture
def api():
    user = User.objects.create_superuser("menu-admin", password="StrongMenuPassword!1")
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.mark.django_db
def test_every_menu_endpoint_is_available(api):
    endpoints = [
        "departments", "roles", "users", "business-groups", "tags",
        "business-systems", "monitors", "monitor-results", "business-chains",
        "incidents", "alert-rules", "notification-channels", "notification-logs",
        "maintenance-windows", "status-pages", "audit-logs", "login-records",
    ]
    for endpoint in endpoints:
        assert api.get(f"/api/v1/{endpoint}/").status_code == 200, endpoint
    assert api.get("/api/v1/dashboard/summary/").status_code == 200
    assert api.get("/api/v1/reports/sla/").status_code == 200
    assert api.get("/health/ready").status_code == 200
    overview = api.get("/api/v1/system/overview/")
    assert overview.status_code == 200
    assert {"database", "redis", "task_queue", "scheduler"} <= set(overview.data["components"])
    assert overview.data["retention"]["monitor_results"] == 10000


@pytest.mark.django_db
def test_login_success_and_failure_are_recorded(api):
    login = APIClient()
    success = login.post(
        "/api/v1/auth/login/",
        {"username": "menu-admin", "password": "StrongMenuPassword!1"},
        format="json",
        HTTP_X_REAL_IP="203.0.113.10",
        HTTP_USER_AGENT="Login record test agent",
    )
    assert success.status_code == 200
    assert LoginRecord.objects.filter(
        username="menu-admin", source_ip="203.0.113.10", success=True
    ).exists()

    failed = login.post(
        "/api/v1/auth/login/",
        {"username": "menu-admin", "password": "incorrect-password"},
        format="json",
        HTTP_X_REAL_IP="203.0.113.11",
    )
    assert failed.status_code == 401
    failure = LoginRecord.objects.get(source_ip="203.0.113.11")
    assert not failure.success
    assert failure.failure_reason == "INVALID_CREDENTIALS"

    records = api.get("/api/v1/login-records/?ordering=-created_at")
    assert records.status_code == 200
    assert records.data["count"] == 2


@pytest.mark.django_db
def test_system_brand_settings_can_be_read_and_updated(api):
    initial = api.get("/api/v1/system/settings/")
    assert initial.status_code == 200
    assert initial.data["brand_logo_text"] == "合力数据"
    response = api.patch(
        "/api/v1/system/settings/",
        {
            "brand_logo_text": "合力监控",
            "home_page_title": "业务可用性平台",
            "browser_title": "合力业务监控",
            "login_page_description": "统一业务可用性监控入口",
            "monitor_wall_title": "业务运行指挥中心",
            "dashboard_refresh_seconds": 60,
            "monitor_wall_refresh_seconds": 15,
            "monitor_result_retention_count": 20000,
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.data["brand_logo_text"] == "合力监控"
    assert response.data["home_page_title"] == "业务可用性平台"
    assert response.data["browser_title"] == "合力业务监控"
    assert response.data["dashboard_refresh_seconds"] == 60
    assert response.data["monitor_result_retention_count"] == 20000
    assert response.data["monitor_wall_title"] == "业务运行指挥中心"
    assert AuditLog.objects.filter(action="UPDATE", resource_type="SystemSetting").exists()
    anonymous = APIClient().get("/api/v1/public/branding/")
    assert anonymous.status_code == 200
    assert anonymous.data == {
        "brand_logo_text": "合力监控",
        "home_page_title": "业务可用性平台",
        "browser_title": "合力业务监控",
        "login_page_description": "统一业务可用性监控入口",
    }


@pytest.mark.django_db
def test_system_maintenance_requires_manage_permission(api):
    from apps.accounts.models import Role

    viewer = User.objects.create_user("system-viewer", password="StrongViewerPass!1")
    Role.objects.create(
        name="系统只读", code="SYSTEM_VIEWER", permissions=["system.view"]
    ).users.add(viewer)
    readonly = APIClient()
    readonly.force_authenticate(viewer)
    assert readonly.get("/api/v1/system/overview/").status_code == 200
    assert readonly.post(
        "/api/v1/system/maintenance/", {"operation": "cleanup_results"}, format="json"
    ).status_code == 403
    with patch("apps.core.api.cleanup_monitor_results.delay") as delay:
        delay.return_value.id = "task-1"
        response = api.post(
            "/api/v1/system/maintenance/", {"operation": "cleanup_results"}, format="json"
        )
    assert response.status_code == 202
    assert response.data["task_id"] == "task-1"


@pytest.mark.django_db
def test_all_monitor_types_can_be_created_edited_and_tested(api):
    business = BusinessSystem.objects.create(name="全类型探测测试", code="ALL-PROBES")
    cases = {
        "HTTP": ("http://example.com/health", {"expected_status": [200]}),
        "API": ("https://example.com/api/health", {"method": "GET", "auth": {"type": "none"}}),
        "TCP": ("example.com:80", {"send": "", "expect": ""}),
        "PING": ("192.0.2.1", {"count": 3}),
        "DNS": ("example.com", {"record_type": "A", "expected": []}),
        "SSL": ("example.com:443", {"warn_days": 30}),
        "MSSQL": (
            "192.0.2.10:1433",
            {"database": "master", "username": "u", "password": "p", "query": "SELECT 1"},
        ),
        "POSTGRESQL": (
            "192.0.2.11:5432",
            {"database": "postgres", "username": "u", "password": "p", "query": "SELECT 1"},
        ),
        "MYSQL": (
            "192.0.2.12:3306",
            {"database": "mysql", "username": "u", "password": "p", "query": "SELECT 1"},
        ),
        "MONGODB": ("192.0.2.13:27017", {"database": "admin", "username": "u", "password": "p"}),
    }
    with patch(
        "apps.core.tasks.execute_probe",
        return_value={"success": True, "latency_ms": 1.25, "metrics": {}, "detail": {}},
    ):
        for monitor_type, (target, config) in cases.items():
            created = api.post(
                "/api/v1/monitors/",
                {
                    "business": str(business.id),
                    "name": f"{monitor_type} 探测",
                    "monitor_type": monitor_type,
                    "target": target,
                    "interval_seconds": 60,
                    "timeout_seconds": 10,
                    "config": config,
                },
                format="json",
            )
            assert created.status_code == 201, (monitor_type, created.data)
            monitor_id = created.data["id"]
            edited = api.patch(
                f"/api/v1/monitors/{monitor_id}/",
                {"name": f"{monitor_type} 探测（已编辑）"},
                format="json",
            )
            assert edited.status_code == 200, (monitor_type, edited.data)
            tested = api.post(f"/api/v1/monitors/{monitor_id}/test/")
            assert tested.status_code == 200, (monitor_type, tested.data)
            assert tested.data["success"] is True


@pytest.mark.django_db
def test_crud_forms_and_key_actions(api):
    department = api.post(
        "/api/v1/departments/", {"name": "测试部门", "code": "QA"}, format="json"
    )
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
            "business": business.data["id"], "name": "存活探测", "monitor_type": "HTTP",
            "target": "http://192.168.31.61/health/live", "interval_seconds": 60,
            "timeout_seconds": 10, "tags": [tag.data["id"]],
        },
        format="json",
    )
    assert monitor.status_code == 201
    with patch(
        "apps.core.tasks.execute_probe", return_value={"success": True, "status_code": 200}
    ):
        assert api.post(f"/api/v1/monitors/{monitor.data['id']}/test/").data["success"]
    assert api.patch(f"/api/v1/tags/{tag.data['id']}/", {"name": "核心系统"}).status_code == 200
    assert api.delete(f"/api/v1/tags/{tag.data['id']}/").status_code == 204


@pytest.mark.django_db
def test_user_password_incident_and_readonly_guards(api):
    current = User.objects.get(username="menu-admin")
    users = api.get("/api/v1/users/")
    current_data = next(item for item in users.data["results"] if item["id"] == current.id)
    assert current_data["data_scope"] == "SELF"
    updated = api.patch(
        f"/api/v1/users/{current.id}/",
        {"data_scope": current_data["data_scope"]},
        format="json",
    )
    assert updated.status_code == 200

    role = api.post(
        "/api/v1/roles/", {"name": "运维人员", "code": "OPERATOR"}, format="json"
    )
    created = api.post(
        "/api/v1/users/",
        {
            "username": "operator1",
            "password": "Op3r!123",
            "is_active": True,
            "roles": [role.data["id"]],
        },
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
    assert User.objects.get(username="operator1").business_roles.filter(code="OPERATOR").exists()
    assert api.delete(f"/api/v1/users/{current.id}/").status_code == 400
    business = BusinessSystem.objects.create(name="事件业务", code="INC-BIZ")
    monitor = Monitor.objects.create(
        business=business, name="事件探测", monitor_type="HTTP", target="http://example.com"
    )
    incident = Incident.objects.create(
        number="INC-TEST-1", monitor=monitor, title="测试事件", severity="HIGH"
    )
    acknowledged = api.post(f"/api/v1/incidents/{incident.id}/acknowledge/")
    assert acknowledged.data["status"] == "ACKNOWLEDGED"
    closed = api.post(
        f"/api/v1/incidents/{incident.id}/close/", {"resolution": "已恢复"}
    )
    assert closed.data["status"] == "CLOSED"
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
    summary = api.get("/api/v1/monitor-results/summary/")
    assert summary.status_code == 200
    assert summary.data["total"] >= 1
    assert summary.data["passed"] + summary.data["failed"] == summary.data["total"]


@pytest.mark.django_db
def test_incident_can_be_deleted_with_timeline_and_audit(api):
    business = BusinessSystem.objects.create(name="事件删除业务", code="INC-DELETE")
    monitor = Monitor.objects.create(
        business=business,
        name="事件删除探测",
        monitor_type="HTTP",
        target="http://example.com/health",
    )
    incident = Incident.objects.create(
        number="INC-DELETE-TEST", monitor=monitor, title="待删除事件", status="RECOVERED"
    )
    IncidentTimeline.objects.create(incident=incident, action="RECOVERED")
    incident_id = str(incident.id)

    response = api.delete(f"/api/v1/incidents/{incident_id}/")

    assert response.status_code == 204
    assert not Incident.objects.filter(pk=incident_id).exists()
    assert not IncidentTimeline.objects.filter(incident_id=incident_id).exists()
    assert AuditLog.objects.filter(
        action="DELETE", resource_type="Incident", resource_id=incident_id
    ).exists()
    assert api.post("/api/v1/audit-logs/", {}, format="json").status_code == 405
