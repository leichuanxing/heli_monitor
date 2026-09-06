import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.businesses.models import BusinessSystem
from apps.core.serializers import MonitorSerializer
from apps.core.tasks import execute_and_record
from apps.monitors.models import Monitor


class Command(BaseCommand):
    help = "创建或更新全类型真实探测任务，并立即执行验证"

    def add_arguments(self, parser):
        parser.add_argument("--include-mssql", action="store_true")

    def handle(self, *args, **options):
        database = settings.DATABASES["default"]
        probe_password = os.getenv("PROBE_DATABASE_PASSWORD", "")
        if not probe_password:
            raise CommandError("必须通过 PROBE_DATABASE_PASSWORD 提供专用数据库测试密码")
        cases = {
            "HTTP": (
                "http://backend:8000/health/live",
                {"expected_status": [200], "headers": {"Host": "192.168.31.61"}},
            ),
            "API": (
                "http://backend:8000/health/ready",
                {
                    "method": "GET",
                    "expected_status": [200],
                    "keywords": ["status"],
                    "headers": {"Host": "192.168.31.61"},
                },
            ),
            "TCP": ("redis:6379", {}),
            "PING": ("backend", {"count": 3}),
            "DNS": ("backend", {"record_type": "A"}),
            "SSL": ("www.baidu.com:443", {"warn_days": 30}),
            "POSTGRESQL": (
                "postgres:5432",
                {
                    "database": database["NAME"],
                    "username": database["USER"],
                    "password": database["PASSWORD"],
                    "query": "SELECT 1",
                    "expected_value": 1,
                    "sslmode": "prefer",
                },
            ),
            "MYSQL": (
                "heli-probe-mysql:3306",
                {
                    "database": "probe",
                    "username": "root",
                    "password": probe_password,
                    "query": "SELECT 1",
                    "expected_value": 1,
                },
            ),
            "MONGODB": (
                "heli-probe-mongo:27017",
                {
                    "database": "admin",
                    "username": "monitor",
                    "password": probe_password,
                    "auth_source": "admin",
                },
            ),
        }
        if options["include_mssql"]:
            cases["MSSQL"] = (
                "heli-probe-mssql:1433",
                {
                    "database": "master",
                    "username": "sa",
                    "password": probe_password,
                    "query": "SELECT 1",
                    "expected_value": 1,
                    "tds_version": "7.4",
                },
            )
        business, _ = BusinessSystem.objects.get_or_create(
            code="PROBE-MATRIX",
            defaults={"name": "全类型探测验证业务", "description": "真实服务探测验证矩阵"},
        )
        failures = []
        for monitor_type, (target, config) in cases.items():
            monitor = Monitor.objects.filter(
                business=business, name=f"全类型验证 - {monitor_type}"
            ).first()
            payload = {
                "business": business.pk,
                "name": f"全类型验证 - {monitor_type}",
                "monitor_type": monitor_type,
                "target": target,
                "interval_seconds": 300,
                "timeout_seconds": 15,
                "failure_threshold": 3,
                "recovery_threshold": 2,
                "config": config,
                "is_enabled": True,
            }
            serializer = (
                MonitorSerializer(monitor, data=payload)
                if monitor
                else MonitorSerializer(data=payload)
            )
            serializer.is_valid(raise_exception=True)
            monitor = serializer.save()
            result = execute_and_record(monitor)
            state = "PASS" if result.success else "FAIL"
            self.stdout.write(
                f"{state} {monitor_type}: {result.latency_ms} ms {result.error_summary or ''}"
            )
            if not result.success:
                failures.append(monitor_type)
        if failures:
            raise CommandError(f"探测未通过：{', '.join(failures)}")
        self.stdout.write(self.style.SUCCESS(f"全部 {len(cases)} 种探测通过"))
