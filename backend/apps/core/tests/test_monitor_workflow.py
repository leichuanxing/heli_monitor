from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.businesses.models import BusinessSystem
from apps.core.models import SystemSetting
from apps.core.monitor_config import host_port, read_query, validate_config
from apps.core.probes import ping_probe, tcp_probe
from apps.core.serializers import MonitorSerializer
from apps.core.state_engine import apply_result
from apps.core.tasks import cleanup_monitor_results
from apps.monitors.models import Monitor, MonitorResult


@pytest.fixture
def monitor(db):
    business = BusinessSystem.objects.create(code="workflow", name="Workflow")
    return Monitor.objects.create(
        business=business, name="HTTP task", monitor_type="HTTP", target="https://example.com"
    )


@pytest.fixture
def api(db):
    client = APIClient()
    client.force_authenticate(User.objects.create_superuser("workflow-admin"))
    return client


def result(monitor, key="result", age=1, success=True, metrics=None):
    at = timezone.now() - timedelta(hours=age)
    return MonitorResult.objects.create(
        monitor=monitor,
        execution_key=key,
        scheduled_at=at,
        started_at=at,
        checked_at=at,
        finished_at=at,
        success=success,
        latency_ms=12,
        metrics=metrics or {},
    )


@pytest.mark.parametrize(
    "target,default,expected",
    [
        ("example.com", 443, ("example.com", 443)),
        ("[2001:db8::1]:5432", 5432, ("2001:db8::1", 5432)),
        ("2001:db8::1", 443, ("2001:db8::1", 443)),
        ("db.internal:3306", 3306, ("db.internal", 3306)),
    ],
)
def test_target_parsing(target, default, expected):
    assert host_port(target, default) == expected


@pytest.mark.parametrize(
    "query",
    [
        "SELECT 1; DELETE FROM t",
        "WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x",
        "WITH x AS (SELECT 1) DELETE FROM t",
        "SELECT * INTO copy FROM source",
    ],
)
def test_write_queries_are_rejected(query):
    with pytest.raises(ValueError):
        read_query(query)


def test_read_only_cte_is_supported():
    assert read_query("WITH x AS (SELECT 1 AS n) SELECT n FROM x")


@pytest.mark.parametrize(
    "config",
    [
        {"expected_status": [99]},
        {"expected_status": ["200"]},
        {"expected_status": [True]},
        {"method": "CONNECT"},
        {"regex": "["},
        {"json_assertions": [{"path": "$["}]},
        {"form": []},
        {"follow_redirects": "false"},
        {"headers": {"X-Test": 123}},
    ],
)
def test_http_configuration_is_validated(config):
    with pytest.raises(ValueError):
        validate_config("HTTP", "https://example.com", config)


def test_ssl_target_without_port_is_valid():
    assert validate_config("SSL", "example.com", {"warn_days": 30}) == {"warn_days": 30}


@pytest.mark.django_db
def test_database_blank_assertion_and_unauthed_mongo(monitor):
    config = validate_config(
        "MYSQL",
        "db:3306",
        {"database": "app", "username": "u", "password": "p", "expected_value": ""},
    )
    assert "expected_value" not in config
    assert validate_config("MONGODB", "mongo:27017", {"database": "admin", "auth_enabled": False})


@pytest.mark.django_db
def test_auth_and_sensitive_headers_are_encrypted_and_preserved(monitor):
    config = {
        "auth": {"type": "bearer", "token": "test-only-token"},
        "headers": {"X-API-Key": "test-only-key"},
    }
    serializer = MonitorSerializer(monitor, data={"config": config}, partial=True)
    assert serializer.is_valid(), serializer.errors
    saved = serializer.save()
    assert saved.config["auth"]["token"].startswith("fernet:v1:")
    assert saved.config["headers"]["X-API-Key"].startswith("fernet:v1:")
    output = MonitorSerializer(saved).data["config"]
    assert output["auth"]["token"] == "********"
    assert output["headers"]["X-API-Key"] == "********"
    update = MonitorSerializer(saved, data={"config": output}, partial=True)
    assert update.is_valid(), update.errors
    assert update.save().config == saved.config


@patch("apps.core.probes.validate_target")
@patch("apps.core.probes.subprocess.run")
def test_ping_loss_threshold_and_bounded_timeout(run, _validate):
    run.return_value = SimpleNamespace(
        returncode=0, stdout="50% packet loss\nrtt min/avg/max/mdev = 1.0/2.0/3.0/1.0 ms"
    )
    assert not ping_probe("server", {"count": 10, "timeout": 5})["success"]
    assert ping_probe("server", {"count": 10, "timeout": 5, "max_packet_loss": 60})["success"]
    assert run.call_args.kwargs["timeout"] == 7
    assert "--" in run.call_args.args[0]


@patch("apps.core.probes.validate_target")
@patch("apps.core.probes.socket.create_connection")
def test_tcp_handles_split_responses_and_escapes(connect, _validate):
    sock = connect.return_value.__enter__.return_value
    sock.recv.side_effect = [b"PO", b"NG"]
    output = tcp_probe(
        "server:6379", {"send": "PING\\r\\n", "send_escapes": True, "expect": "PONG"}
    )
    assert output["success"]
    sock.sendall.assert_called_once_with(b"PING\r\n")


@pytest.mark.django_db
def test_certificate_warning_degrades_state(monitor):
    monitor.monitor_type = "SSL"
    monitor.save()
    assert apply_result(result(monitor, metrics={"warning": True})).status == "DEGRADED"


@pytest.mark.django_db
def test_recent_history_is_preserved_beyond_count(monitor):
    setting = SystemSetting.load()
    setting.monitor_result_retention_count = 1
    setting.save()
    result(monitor, "recent-1", 1)
    result(monitor, "recent-2", 2)
    result(monitor, "old", 40 * 24)
    assert cleanup_monitor_results() == 1
    assert monitor.results.count() == 2


@pytest.mark.django_db
def test_history_filters_range_statistics_and_pagination(api, monitor):
    result(monitor, "pass", 1, True)
    result(monitor, "fail", 2, False)
    response = api.get("/api/v1/monitors/history/", {"monitor": str(monitor.pk), "page_size": 1})
    assert response.status_code == 200
    assert response.data["count"] == 2
    assert len(response.data["results"]) == 1
    assert response.data["summary"]["passed"] == 1
    assert response.data["summary"]["failed"] == 1
    assert response.data["summary"]["availability"] == 50
    assert len(response.data["series"]) == 2
    assert response.data["bucket"] == "raw"
    assert response.data["next"]
    response = api.get(
        "/api/v1/monitors/history/", {"monitor": str(monitor.pk), "success": "false"}
    )
    assert response.data["count"] == 1


@pytest.mark.django_db
def test_history_excludes_archived_monitors(api, monitor):
    result(monitor)
    monitor.is_archived = True
    monitor.is_enabled = False
    monitor.save()
    response = api.get("/api/v1/monitors/history/", {"monitor": str(monitor.pk)})
    assert response.status_code == 200 and response.data["count"] == 0
    assert response.data["summary"]["total"] == 0
    assert response.data["series"] == []
    assert MonitorResult.objects.filter(monitor=monitor).exists()
    all_history = api.get("/api/v1/monitors/history/")
    assert all_history.data["count"] == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "params",
    [
        {"checked_after": "bad"},
        {"monitor": "bad"},
        {"monitor_type": "INVALID"},
        {"checked_after": (timezone.now() - timedelta(days=32)).isoformat()},
        {"checked_before": (timezone.now() + timedelta(days=1)).isoformat()},
    ],
)
def test_history_rejects_invalid_ranges(api, params):
    assert api.get("/api/v1/monitors/history/", params).status_code == 400


@pytest.mark.django_db
def test_history_requires_monitor_permission(monitor):
    client = APIClient()
    client.force_authenticate(User.objects.create_user("no-monitor"))
    assert client.get("/api/v1/monitors/history/").status_code == 403


@pytest.mark.django_db
def test_copy_keeps_config_but_starts_paused(api, monitor):
    response = api.post(f"/api/v1/monitors/{monitor.pk}/copy/", {}, format="json")
    assert response.status_code == 201
    clone = Monitor.objects.get(pk=response.data["id"])
    assert not clone.is_enabled
    assert clone.config == monitor.config
    assert clone.pk != monitor.pk


@pytest.mark.django_db
def test_bulk_enable_validates_boolean_and_ids(api, monitor):
    response = api.post(
        "/api/v1/monitors/bulk-enable/",
        {"ids": [str(monitor.pk)], "enabled": "false"},
        format="json",
    )
    assert response.status_code == 200
    monitor.refresh_from_db()
    assert not monitor.is_enabled
    assert (
        api.post(
            "/api/v1/monitors/bulk-enable/", {"ids": [], "enabled": True}, format="json"
        ).status_code
        == 400
    )
    assert (
        api.post(
            "/api/v1/monitors/bulk-enable/", {"ids": ["bad"], "enabled": True}, format="json"
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_batch_run_and_progress_are_bound_to_user(api, monitor):
    stored = result(monitor)
    with patch("apps.core.monitor_api.execute_monitor.apply_async") as enqueue:
        response = api.post(
            "/api/v1/monitors/run-batch/", {"ids": [str(monitor.pk)]}, format="json"
        )
    assert response.status_code == 202
    enqueue.assert_called_once()
    task = MagicMock()
    task.state = "SUCCESS"
    task.successful.return_value = True
    task.result = stored.pk
    with patch("apps.core.monitor_api.AsyncResult", return_value=task):
        progress = api.get("/api/v1/monitors/batch-status/", {"token": response.data["token"]})
    assert progress.status_code == 200
    assert progress.data["done"] and progress.data["passed"] == 1
    other = APIClient()
    other.force_authenticate(User.objects.create_superuser("other-admin"))
    assert (
        other.get("/api/v1/monitors/batch-status/", {"token": response.data["token"]}).status_code
        == 400
    )
    assert api.get("/api/v1/monitors/batch-status/", {"token": "invalid"}).status_code == 400


@pytest.mark.django_db
def test_batch_rejects_disabled_monitor(api, monitor):
    monitor.is_enabled = False
    monitor.save()
    with patch("apps.core.monitor_api.execute_monitor.apply_async") as enqueue:
        assert (
            api.post(
                "/api/v1/monitors/run-batch/", {"ids": [str(monitor.pk)]}, format="json"
            ).status_code
            == 400
        )
    enqueue.assert_not_called()


@pytest.mark.django_db
def test_bad_configuration_can_still_be_paused(api, monitor):
    monitor.config = {"auth": "invalid"}
    monitor.save()
    response = api.patch(f"/api/v1/monitors/{monitor.pk}/", {"is_enabled": False}, format="json")
    assert response.status_code == 200
    monitor.refresh_from_db()
    assert not monitor.is_enabled


@pytest.mark.django_db
def test_enable_returns_pending_after_cached_state(api, monitor):
    apply_result(result(monitor))
    monitor.is_enabled = False
    monitor.save()
    response = api.patch(f"/api/v1/monitors/{monitor.pk}/", {"is_enabled": True}, format="json")
    assert response.status_code == 200
    assert response.data["current_status"] == "PENDING"
    assert response.data["service_available"] is None


@pytest.mark.django_db
def test_edit_preserves_historical_metadata(api, monitor):
    old = result(monitor)
    response = api.patch(
        f"/api/v1/monitors/{monitor.pk}/",
        {"name": "Renamed task", "target": "https://changed.example.com"},
        format="json",
    )
    assert response.status_code == 200
    history = api.get("/api/v1/monitors/history/", {"monitor": str(monitor.pk)})
    row = history.data["results"][0]
    assert row["id"] == old.pk
    assert row["monitor_name"] == "HTTP task"
    assert row["monitor_target"] == "https://example.com"


@pytest.mark.django_db
def test_history_type_filter_uses_original_probe_type(api, monitor):
    result(monitor)
    response = api.patch(
        f"/api/v1/monitors/{monitor.pk}/",
        {"monitor_type": "TCP", "target": "example.com:443", "config": {}},
        format="json",
    )
    assert response.status_code == 200
    history = api.get(
        "/api/v1/monitors/history/", {"monitor": str(monitor.pk), "monitor_type": "HTTP"}
    )
    assert history.data["count"] == 1
    assert history.data["results"][0]["monitor_type"] == "HTTP"


@pytest.mark.django_db
def test_old_inflight_probe_does_not_update_changed_task(monitor):
    from apps.core.tasks import execute_and_record

    def probe(*args):
        Monitor.objects.filter(pk=monitor.pk).update(target="https://changed.example.com")
        return {"success": True}

    with (
        patch("apps.core.tasks.execute_probe", side_effect=probe),
        patch("apps.core.tasks.apply_result") as apply,
    ):
        recorded = execute_and_record(monitor)
    apply.assert_not_called()
    assert recorded.monitor_snapshot["target"] == "https://example.com"


@pytest.mark.django_db
def test_legacy_inserts_receive_snapshot_database_default(monitor):
    from django.db import connection

    now = timezone.now()
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO monitors_monitorresult
            (monitor_id,execution_key,scheduled_at,started_at,checked_at,finished_at,success,metrics,assertions,detail)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'{}','[]','{}')""",
            [monitor.pk, "legacy-default", now, now, now, now, True],
        )
    assert MonitorResult.objects.get(execution_key="legacy-default").monitor_snapshot == {}


@pytest.mark.django_db
def test_editing_interval_reschedules_immediately(api, monitor):
    apply_result(result(monitor))
    Monitor.objects.filter(pk=monitor.pk).update(next_run_at=timezone.now() + timedelta(hours=1))
    response = api.patch(f"/api/v1/monitors/{monitor.pk}/", {"interval_seconds": 30}, format="json")
    assert response.status_code == 200
    monitor.refresh_from_db()
    assert monitor.next_run_at <= timezone.now()
    assert response.data["current_status"] == "PENDING"


@pytest.mark.django_db
def test_batch_keeps_partial_submission_progress(api, monitor):
    from django.core import signing
    from kombu.exceptions import OperationalError

    second = Monitor.objects.create(
        business=monitor.business, name="Second", monitor_type="HTTP", target="https://example.com"
    )
    with patch(
        "apps.core.monitor_api.execute_monitor.apply_async",
        side_effect=[None, OperationalError("private broker details")],
    ):
        response = api.post(
            "/api/v1/monitors/run-batch/", {"ids": [str(monitor.pk), str(second.pk)]}, format="json"
        )
    assert response.status_code == 202
    payload = signing.loads(response.data["token"], salt="monitor-batch")
    assert len(payload["tasks"]) == 2
    assert not payload["tasks"][0].get("submission_failed")
    assert payload["tasks"][1]["submission_failed"]
    task = MagicMock(state="PENDING")
    task.successful.return_value = False
    with patch("apps.core.monitor_api.AsyncResult", return_value=task):
        progress = api.get("/api/v1/monitors/batch-status/", {"token": response.data["token"]})
    assert progress.data["completed"] == 1
    assert progress.data["failed"] == 1
    assert not progress.data["done"]
    assert "private broker" not in str(progress.data)


@pytest.mark.django_db
def test_batch_pending_result_has_deadline(api, monitor):
    from django.core import signing

    token = signing.dumps(
        {
            "user": User.objects.get(username="workflow-admin").pk,
            "submitted_at": (timezone.now() - timedelta(minutes=32)).isoformat(),
            "tasks": [{"monitor": str(monitor.pk), "name": monitor.name, "task": "expired"}],
        },
        salt="monitor-batch",
    )
    task = MagicMock(state="PENDING")
    task.successful.return_value = False
    with patch("apps.core.monitor_api.AsyncResult", return_value=task):
        response = api.get("/api/v1/monitors/batch-status/", {"token": token})
    assert response.data["done"] and response.data["failed"] == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "params",
    [
        {"checked_after": "bad-date"},
        {"checked_before": "bad-date"},
        {"monitor_type": "INVALID"},
        {"checked_after": "2026-10-20T10:00:00Z", "checked_before": "2026-10-19T10:00:00Z"},
    ],
)
def test_result_filters_reject_invalid_input(api, params):
    assert api.get("/api/v1/monitor-results/", params).status_code == 400
    assert api.get("/api/v1/monitor-results/summary/", params).status_code == 400


@pytest.mark.django_db
def test_result_summary_uses_execution_type(api, monitor):
    old = result(monitor)
    old.monitor_snapshot = {"monitor_type": "DNS"}
    old.save(update_fields=["monitor_snapshot"])
    result(monitor, key="current")
    response = api.get("/api/v1/monitor-results/summary/")
    assert response.status_code == 200
    assert {row["type"]: row["total"] for row in response.data["by_type"]} == {"HTTP": 1, "DNS": 1}


@pytest.mark.django_db
def test_permanent_delete_clears_dependents_but_keeps_other_tasks(api, monitor):
    from apps.alerts.models import NotificationChannel, NotificationLog
    from apps.core.monitor_deletion import delete_monitor
    from apps.incidents.models import Incident, IncidentTimeline
    from apps.monitors.models import BusinessChain, ChainEdge, ChainNode, StateTransition

    stored = result(monitor)
    StateTransition.objects.create(
        monitor=monitor, result=stored, from_status="UP", to_status="DOWN"
    )
    incident = Incident.objects.create(number="PURGE-TEST", monitor=monitor, title="Failure")
    IncidentTimeline.objects.create(incident=incident, action="OPENED")
    channel = NotificationChannel.objects.create(name="Purge channel", channel_type="WEBHOOK")
    NotificationLog.objects.create(incident=incident, channel=channel)
    other = Monitor.objects.create(
        business=monitor.business, name="Other", monitor_type="TCP", target="example.com:443"
    )
    other_result = result(other, key="other-purge-result")
    chain = BusinessChain.objects.create(business=monitor.business, name="Chain")
    first = ChainNode.objects.create(chain=chain, monitor=monitor, name="Deleted")
    second = ChainNode.objects.create(chain=chain, monitor=other, name="Keep")
    ChainEdge.objects.create(chain=chain, source=first, target=second)
    delete_monitor(monitor.pk)
    assert not Monitor.objects.filter(pk=monitor.pk).exists()
    assert not MonitorResult.objects.filter(pk=stored.pk).exists()
    assert not StateTransition.objects.filter(monitor_id=monitor.pk).exists()
    assert not Incident.objects.filter(pk=incident.pk).exists()
    assert not NotificationLog.objects.filter(incident_id=incident.pk).exists()
    assert not ChainEdge.objects.filter(chain=chain).exists()
    assert ChainNode.objects.filter(pk=second.pk).exists()
    assert MonitorResult.objects.filter(pk=other_result.pk).exists()
    assert NotificationChannel.objects.filter(pk=channel.pk).exists()


@pytest.mark.django_db
def test_deleted_monitor_queued_probe_is_skipped(monitor):
    from apps.core.monitor_deletion import delete_monitor
    from apps.core.tasks import execute_monitor

    key = str(monitor.pk)
    delete_monitor(key)
    with patch("apps.core.tasks.execute_probe") as probe:
        assert execute_monitor.run(key, timezone.now().isoformat()) == "deleted"
    probe.assert_not_called()


@pytest.mark.django_db
def test_delete_during_probe_cannot_recreate_results(monitor):
    from apps.core.monitor_deletion import delete_monitor
    from apps.core.tasks import execute_monitor

    key = str(monitor.pk)

    def finish_probe(*args):
        delete_monitor(key)
        return {"success": True}

    with patch("apps.core.tasks.execute_probe", side_effect=finish_probe):
        assert execute_monitor.run(key, timezone.now().isoformat()) == "deleted"
    assert not MonitorResult.objects.filter(monitor_id=key).exists()


@pytest.mark.django_db
def test_history_chart_preserves_each_original_point_beyond_page(api, monitor):
    first = result(monitor, key="raw-first")
    second = result(monitor, key="raw-second", success=False)
    # Even identical timestamps must remain separate records, without averaging.
    at = timezone.now() - timedelta(minutes=2)
    MonitorResult.objects.filter(pk=first.pk).update(checked_at=at, latency_ms=1.25)
    MonitorResult.objects.filter(pk=second.pk).update(checked_at=at, latency_ms=999.75)
    response = api.get("/api/v1/monitors/history/", {"monitor": str(monitor.pk), "page_size": 1})
    assert response.status_code == 200
    assert response.data["bucket"] == "raw"
    assert len(response.data["results"]) == 1
    points = response.data["series"]
    assert len(points) == response.data["summary"]["total"] == 2
    assert [p["id"] for p in points] == [first.pk, second.pk]
    assert [p["latency_ms"] for p in points] == [1.25, 999.75]
    assert [p["success"] for p in points] == [True, False]
    assert points[0]["at"] == points[1]["at"] == at


@pytest.mark.django_db
def test_dashboard_pending_and_disabled_business_match_task_state(api, monitor):
    from apps.monitors.models import MonitorState

    stored = result(monitor)
    MonitorState.objects.create(monitor=monitor, status="PENDING", last_result=stored)
    response = api.get("/api/v1/dashboard/summary/")
    row = response.data["latest_monitors"][0]
    assert row["status"] == "PENDING" and row["available"] is None
    monitor.business.is_enabled = False
    monitor.business.save()
    row = api.get("/api/v1/dashboard/summary/").data["latest_monitors"][0]
    assert row["status"] == "PAUSED" and row["available"] is None
    serialized = MonitorSerializer(monitor).data
    assert serialized["current_status"] == "PAUSED"


@pytest.mark.django_db
def test_chain_rejects_cross_chain_self_loop_and_cycles(api, monitor):
    from apps.monitors.models import BusinessChain, ChainEdge, ChainNode

    chain = BusinessChain.objects.create(business=monitor.business, name="Chain")
    other = BusinessChain.objects.create(business=monitor.business, name="Other")
    nodes = [
        ChainNode.objects.create(
            chain=chain,
            monitor=Monitor.objects.create(
                business=monitor.business, name=str(i), monitor_type="TCP", target="example.com:443"
            ),
            name=str(i),
        )
        for i in range(3)
    ]
    alien = ChainNode.objects.create(chain=other, monitor=monitor, name="Alien")

    def edge(a, b):
        return api.post(
            "/api/v1/chain-edges/",
            {"chain": str(chain.pk), "source": a.pk, "target": b.pk},
            format="json",
        )

    assert edge(nodes[0], alien).status_code == 400
    assert edge(nodes[0], nodes[0]).status_code == 400
    assert edge(nodes[0], nodes[1]).status_code == 201
    assert edge(nodes[1], nodes[2]).status_code == 201
    assert edge(nodes[2], nodes[0]).status_code == 400
    assert (
        api.patch(
            f"/api/v1/chain-nodes/{nodes[0].pk}/", {"chain": str(other.pk)}, format="json"
        ).status_code
        == 400
    )
    existing = ChainEdge.objects.get(source=nodes[0])
    assert (
        api.patch(
            f"/api/v1/chain-edges/{existing.pk}/", {"target": alien.pk}, format="json"
        ).status_code
        == 400
    )
