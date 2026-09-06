from unittest.mock import MagicMock, patch

import pytest

from apps.businesses.models import BusinessSystem
from apps.core.probes import database_probe, execute_probe
from apps.core.serializers import MonitorSerializer


@pytest.mark.parametrize(
    ("kind", "target", "config"),
    [
        ("MSSQL", "10.0.0.10:1433", {"database": "master", "username": "u", "password": "p"}),
        (
            "POSTGRESQL",
            "10.0.0.11:5432",
            {"database": "postgres", "username": "u", "password": "p"},
        ),
        ("MYSQL", "10.0.0.12:3306", {"database": "mysql", "username": "u", "password": "p"}),
        ("MONGODB", "10.0.0.13:27017", {"database": "admin", "username": "u", "password": "p"}),
    ],
)
def test_execute_probe_routes_database_types(kind, target, config):
    with patch("apps.core.probes.database_probe", return_value={"success": True}) as probe:
        result = execute_probe(kind, target, config)
    assert result["success"] is True
    probe.assert_called_once_with(kind, target, config)


@patch("apps.core.probes.validate_target")
@patch("apps.core.probes.psycopg.connect")
def test_postgresql_probe_connects_and_executes_read_query(connect, _validate):
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchone.return_value = (1,)
    connect.return_value.cursor.return_value = cursor

    result = database_probe(
        "POSTGRESQL",
        "db.internal:5432",
        {
            "database": "app",
            "username": "monitor",
            "password": "secret",
            "query": "SELECT 1",
            "expected_value": 1,
        },
    )

    assert result["success"] is True
    cursor.execute.assert_called_once_with("SELECT 1")
    assert result["detail"]["host"] == "db.internal"
    assert result["detail"]["port"] == 5432
    assert result["detail"]["database"] == "app"
    assert result["metrics"]["connection_time_ms"] >= 0
    assert result["metrics"]["query_time_ms"] >= 0
    assert result["detail"]["query_time_ms"] == result["metrics"]["query_time_ms"]


@patch("apps.core.probes.validate_target")
@patch("apps.core.probes.MongoClient")
def test_mongodb_probe_uses_ping(client_class, _validate):
    client = client_class.return_value
    client.__getitem__.return_value.command.return_value = {"ok": 1.0}

    result = database_probe(
        "MONGODB",
        "mongo.internal:27017",
        {"database": "admin", "username": "monitor", "password": "secret"},
    )

    assert result["success"] is True
    client.__getitem__.return_value.command.assert_called_once_with("ping")


def test_database_probe_rejects_missing_credentials():
    result = database_probe("MYSQL", "10.0.0.12:3306", {"database": "mysql"})
    assert result["success"] is False
    assert result["error_type"] == "INVALID_TARGET"


@pytest.mark.django_db
def test_database_monitor_serializer_masks_and_preserves_password():
    business = BusinessSystem.objects.create(code="db-probe", name="数据库探测业务")
    serializer = MonitorSerializer(
        data={
            "business": business.id,
            "name": "PostgreSQL 可用性",
            "monitor_type": "POSTGRESQL",
            "target": "10.0.0.11:5432",
            "interval_seconds": 60,
            "timeout_seconds": 10,
            "config": {
                "database": "app",
                "username": "monitor",
                "password": "real-secret",
                "query": "SELECT 1",
            },
        }
    )
    assert serializer.is_valid(), serializer.errors
    monitor = serializer.save()
    encrypted_password = monitor.config["password"]
    assert encrypted_password.startswith("fernet:v1:")
    assert "real-secret" not in encrypted_password
    assert MonitorSerializer(monitor).data["config"]["password"] == "********"

    update = MonitorSerializer(
        monitor,
        data={"config": {**monitor.config, "password": "********"}},
        partial=True,
    )
    assert update.is_valid(), update.errors
    assert update.save().config["password"] == encrypted_password


@pytest.mark.django_db
def test_database_monitor_rejects_write_query():
    business = BusinessSystem.objects.create(code="db-write", name="数据库写入校验")
    serializer = MonitorSerializer(
        data={
            "business": business.id,
            "name": "危险 SQL",
            "monitor_type": "MYSQL",
            "target": "10.0.0.12:3306",
            "interval_seconds": 60,
            "timeout_seconds": 10,
            "config": {
                "database": "app",
                "username": "monitor",
                "password": "secret",
                "query": "DELETE FROM orders",
            },
        }
    )
    assert not serializer.is_valid()
    assert "仅允许 SELECT 或 WITH" in str(serializer.errors)
