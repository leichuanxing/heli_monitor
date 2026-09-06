# ruff: noqa: F405
import csv
import hashlib
import secrets
import time
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import connection
from django.db.models import Avg, Count, Q
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from redis import Redis
from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from apps.accounts.models import Department, Role
from apps.alerts.models import AlertRule, NotificationChannel, NotificationLog
from apps.audit.models import AuditLog, LoginRecord
from apps.businesses.models import BusinessGroup, BusinessSystem, Tag
from apps.incidents.models import Incident, IncidentTimeline
from apps.maintenance.models import MaintenanceWindow
from apps.monitors.models import (
    BusinessChain,
    ChainEdge,
    ChainNode,
    Monitor,
    MonitorResult,
)
from apps.status_pages.models import StatusPage

from .models import SystemSetting
from .notifications import send_notification, send_test_notification
from .permissions import (
    PERMISSION_CATALOG,
    HasSystemManagePermission,
    HasSystemViewPermission,
    IsOperatorOrReadOnly,
    user_permissions,
)
from .serializers import *  # noqa: F403
from .tasks import (
    cleanup_monitor_results,
    deliver_notification,
    execute_and_record,
    reconcile_incident_notifications,
)


class BaseViewSet(viewsets.ModelViewSet):
    permission_classes = [IsOperatorOrReadOnly]
    ordering_fields = ["created_at", "updated_at", "name", "status"]
    ordering = ["pk"]

    def perform_create(self, serializer):
        obj = serializer.save()
        AuditLog.objects.create(
            actor=self.request.user,
            action="CREATE",
            resource_type=obj.__class__.__name__,
            resource_id=str(obj.pk),
            request_id=getattr(self.request, "request_id", ""),
            source_ip=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_update(self, serializer):
        obj = serializer.save()
        AuditLog.objects.create(
            actor=self.request.user,
            action="UPDATE",
            resource_type=obj.__class__.__name__,
            resource_id=str(obj.pk),
            request_id=getattr(self.request, "request_id", ""),
            source_ip=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_destroy(self, instance):
        AuditLog.objects.create(
            actor=self.request.user,
            action="DELETE",
            resource_type=instance.__class__.__name__,
            resource_id=str(instance.pk),
            request_id=getattr(self.request, "request_id", ""),
            source_ip=self.request.META.get("REMOTE_ADDR"),
        )
        instance.delete()


class ReadOnlyBaseViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsOperatorOrReadOnly]
    ordering_fields = ["created_at", "updated_at", "name", "status"]
    ordering = ["pk"]


class LoginRecordViewSet(ReadOnlyBaseViewSet):
    queryset = LoginRecord.objects.select_related("user").all()
    serializer_class = LoginRecordSerializer
    permission_classes = [HasSystemViewPermission]
    search_fields = ("username", "source_ip", "user_agent")
    filterset_fields = ("success", "user")
    ordering_fields = ("created_at", "username", "success")
    ordering = ("-created_at",)

    def get_queryset(self):
        queryset = super().get_queryset()
        if value := self.request.query_params.get("created_after"):
            queryset = queryset.filter(created_at__gte=value)
        if value := self.request.query_params.get("created_before"):
            queryset = queryset.filter(created_at__lte=value)
        return queryset


def make_viewset(model, serializer, search=(), filters=()):
    attrs = {
        "queryset": model.objects.all(),
        "serializer_class": serializer,
        "search_fields": search,
        "filterset_fields": filters,
    }
    return type(f"{model.__name__}ViewSet", (BaseViewSet,), attrs)


def make_readonly_viewset(model, serializer, search=(), filters=()):
    attrs = {
        "queryset": model.objects.all(),
        "serializer_class": serializer,
        "search_fields": search,
        "filterset_fields": filters,
    }
    return type(f"{model.__name__}ViewSet", (ReadOnlyBaseViewSet,), attrs)


class DepartmentViewSet(BaseViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    search_fields = ("name", "code", "description")
    filterset_fields = ("parent", "is_enabled")
    ordering = ("sort_order", "name")

    def get_queryset(self):
        return Department.objects.select_related("parent").annotate(user_count=Count("userprofile"))

    def perform_destroy(self, instance):
        try:
            super().perform_destroy(instance)
        except ProtectedError as exc:
            raise ValidationError({"detail": "该部门存在下级部门，不能删除"}) from exc


class RoleViewSet(BaseViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    search_fields = ("name", "code", "description")
    filterset_fields = ("is_enabled", "data_scope")

    def get_queryset(self):
        return Role.objects.annotate(user_count=Count("users")).prefetch_related("users")

    @action(detail=False, methods=["get"], url_path="permission-catalog")
    def permission_catalog(self, request):
        return Response(PERMISSION_CATALOG)


class UserViewSet(BaseViewSet):
    queryset = (
        User.objects.select_related("profile", "profile__department")
        .prefetch_related("business_roles")
        .all()
    )
    serializer_class = UserSerializer
    search_fields = ("username", "first_name", "last_name", "email")
    filterset_fields = ("is_active", "business_roles", "profile__department")

    def perform_destroy(self, instance):
        if instance == self.request.user:
            raise ValidationError({"detail": "不能删除当前登录用户"})
        if (
            instance.is_superuser
            and User.objects.filter(is_superuser=True, is_active=True).count() <= 1
        ):
            raise ValidationError({"detail": "不能删除最后一个有效超级管理员"})
        super().perform_destroy(instance)


@extend_schema(responses={200: UserSerializer})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def current_user(request):
    return Response(
        {
            **UserSerializer(request.user).data,
            "permissions": sorted(user_permissions(request.user)),
        }
    )


BusinessGroupViewSet = make_viewset(BusinessGroup, BusinessGroupSerializer, ("name",))
TagViewSet = make_viewset(Tag, TagSerializer, ("name",))
BusinessSystemViewSet = make_viewset(
    BusinessSystem,
    BusinessSystemSerializer,
    ("name", "code", "description"),
    ("group", "department", "owner", "level", "environment", "is_enabled", "is_archived"),
)


class MonitorResultViewSet(ReadOnlyBaseViewSet):
    queryset = MonitorResult.objects.select_related("monitor", "monitor__business").all()
    serializer_class = MonitorResultSerializer
    search_fields = ("monitor__name", "monitor__target", "monitor__business__name", "error_summary")
    filterset_fields = ("monitor", "success", "error_type")
    ordering_fields = ("checked_at", "latency_ms", "status_code")
    ordering = ("-checked_at",)

    def get_queryset(self):
        qs = super().get_queryset().filter(monitor__is_archived=False)
        checked_after = self.request.query_params.get("checked_after")
        checked_before = self.request.query_params.get("checked_before")
        monitor_type = self.request.query_params.get("monitor_type")
        if checked_after:
            qs = qs.filter(checked_at__gte=checked_after)
        if checked_before:
            qs = qs.filter(checked_at__lte=checked_before)
        if monitor_type:
            qs = qs.filter(monitor__monitor_type=monitor_type)
        return qs

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Return statistics for the complete filtered result set, not only one page."""
        qs = self.filter_queryset(self.get_queryset())
        totals = qs.aggregate(
            total=Count("id"),
            passed=Count("id", filter=Q(success=True)),
            failed=Count("id", filter=Q(success=False)),
            average_latency_ms=Avg("latency_ms"),
        )
        total = totals["total"] or 0
        by_type = list(
            qs.values("monitor__monitor_type")
            .annotate(total=Count("id"), failed=Count("id", filter=Q(success=False)))
            .order_by("monitor__monitor_type")
        )
        errors = list(
            qs.filter(success=False)
            .values("error_type")
            .annotate(count=Count("id"))
            .order_by("-count")[:8]
        )
        return Response(
            {
                **totals,
                "success_rate": round((totals["passed"] or 0) / total * 100, 2) if total else None,
                "by_type": [
                    {
                        "type": row["monitor__monitor_type"],
                        "total": row["total"],
                        "failed": row["failed"],
                    }
                    for row in by_type
                ],
                "errors": errors,
            }
        )


BusinessChainViewSet = make_viewset(
    BusinessChain, BusinessChainSerializer, ("name",), ("business", "is_enabled")
)
ChainNodeViewSet = make_viewset(
    ChainNode, ChainNodeSerializer, ("name",), ("chain", "monitor", "is_critical")
)
ChainEdgeViewSet = make_viewset(ChainEdge, ChainEdgeSerializer, (), ("chain", "source", "target"))


class MaintenanceWindowViewSet(BaseViewSet):
    queryset = MaintenanceWindow.objects.prefetch_related("businesses", "monitors").all()
    serializer_class = MaintenanceWindowSerializer
    search_fields = ("name", "reason", "businesses__name", "monitors__name")
    filterset_fields = ("is_enabled", "exclude_from_sla", "suppress_notifications")
    ordering_fields = ("start_at", "end_at", "name")
    ordering = ("-start_at",)

    def get_queryset(self):
        qs = super().get_queryset()
        state = self.request.query_params.get("state")
        now = timezone.now()
        if state == "ACTIVE":
            qs = qs.filter(is_enabled=True, start_at__lte=now, end_at__gte=now)
        elif state == "UPCOMING":
            qs = qs.filter(is_enabled=True, start_at__gt=now)
        elif state == "ENDED":
            qs = qs.filter(end_at__lt=now)
        return qs.distinct()


class AuditLogViewSet(ReadOnlyBaseViewSet):
    queryset = AuditLog.objects.select_related("actor").all()
    serializer_class = AuditLogSerializer
    search_fields = ("action", "resource_type", "resource_id", "actor__username", "source_ip")
    filterset_fields = ("actor", "action", "resource_type", "result")
    ordering_fields = ("created_at", "action", "resource_type", "result")
    ordering = ("-created_at",)

    def get_queryset(self):
        qs = super().get_queryset()
        if value := self.request.query_params.get("created_after"):
            qs = qs.filter(created_at__gte=value)
        if value := self.request.query_params.get("created_before"):
            qs = qs.filter(created_at__lte=value)
        return qs


def _timed_check(callback):
    started = time.perf_counter()
    try:
        callback()
        return {"status": "ok", "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
    except Exception as exc:
        return {"status": "error", "message": str(exc)[:160]}


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
@permission_classes([HasSystemViewPermission])
def system_overview(request):
    database = _timed_check(lambda: connection.ensure_connection())
    redis_client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
    redis_status = _timed_check(redis_client.ping)
    queue_depth = None
    if redis_status["status"] == "ok":
        try:
            queue_depth = redis_client.llen("celery")
        except Exception:
            pass
    latest_result = MonitorResult.objects.order_by("-checked_at").first()
    open_statuses = ("NEW", "ACKNOWLEDGED", "PROCESSING")
    components = {
        "database": database,
        "redis": redis_status,
        "task_queue": {
            "status": redis_status["status"],
            "pending": queue_depth,
            "message": "队列可连接" if redis_status["status"] == "ok" else "消息队列不可连接",
        },
        "scheduler": {
            "status": "ok"
            if latest_result and latest_result.checked_at >= timezone.now() - timedelta(minutes=10)
            else "warning",
            "last_probe_at": latest_result.checked_at if latest_result else None,
            "message": "最近 10 分钟存在探测结果"
            if latest_result and latest_result.checked_at >= timezone.now() - timedelta(minutes=10)
            else "最近 10 分钟没有探测结果",
        },
    }
    overall = "ok" if all(v["status"] == "ok" for v in components.values()) else "warning"
    return Response(
        {
            "status": overall,
            "checked_at": timezone.now(),
            "environment": settings.SPECTACULAR_SETTINGS.get("VERSION", "unknown"),
            "components": components,
            "statistics": {
                "users": User.objects.filter(is_active=True).count(),
                "active_monitors": Monitor.objects.filter(
                    is_enabled=True, is_archived=False
                ).count(),
                "monitor_results": MonitorResult.objects.count(),
                "open_incidents": Incident.objects.filter(status__in=open_statuses).count(),
                "failed_notifications": NotificationLog.objects.filter(status="FAILED").count(),
                "audit_logs": AuditLog.objects.count(),
            },
            "retention": {
                "monitor_results": SystemSetting.load().monitor_result_retention_count
            },
            "permissions": {"can_manage": "system.manage" in user_permissions(request.user)},
        }
    )


@extend_schema(request=OpenApiTypes.OBJECT, responses={202: OpenApiTypes.OBJECT})
@api_view(["POST"])
@permission_classes([HasSystemManagePermission])
def system_maintenance(request):
    operation = request.data.get("operation")
    task_map = {
        "cleanup_results": cleanup_monitor_results,
        "reconcile_notifications": reconcile_incident_notifications,
    }
    if operation == "retry_failed_notifications":
        ids = list(
            NotificationLog.objects.filter(status="FAILED").values_list("id", flat=True)[:500]
        )
        for item_id in ids:
            deliver_notification.delay(item_id)
        queued = len(ids)
    elif operation in task_map:
        result = task_map[operation].delay()
        queued = 1
        result_id = result.id
    else:
        raise ValidationError({"operation": "不支持的维护操作"})
    AuditLog.objects.create(
        actor=request.user,
        action="MAINTENANCE",
        resource_type="System",
        resource_id=operation,
        detail={"queued": queued},
        request_id=getattr(request, "request_id", ""),
        source_ip=request.META.get("REMOTE_ADDR"),
    )
    return Response(
        {"operation": operation, "queued": queued, "task_id": locals().get("result_id")}, status=202
    )


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
@api_view(["GET", "PATCH"])
def system_settings(request):
    permission = (
        HasSystemViewPermission() if request.method == "GET" else HasSystemManagePermission()
    )
    if not permission.has_permission(request, system_settings):
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied()
    setting = SystemSetting.load()
    if request.method == "PATCH":
        text_fields = {
            "brand_logo_text": (32, "左上角 Logo 文本"),
            "home_page_title": (64, "首页标题"),
            "browser_title": (64, "浏览器标题"),
            "login_page_description": (128, "登录页说明"),
            "monitor_wall_title": (64, "监控大屏标题"),
        }
        number_fields = {
            "dashboard_refresh_seconds": (5, 300, "监控总览刷新周期"),
            "monitor_wall_refresh_seconds": (5, 300, "监控大屏刷新周期"),
            "monitor_result_retention_count": (100, 1000000, "单任务探测结果保留数"),
        }
        changed = {}
        errors = {}
        for field, (max_length, label) in text_fields.items():
            if field not in request.data:
                continue
            value = str(request.data[field]).strip()
            if not value:
                errors[field] = f"{label}不能为空"
            elif len(value) > max_length:
                errors[field] = f"{label}不能超过 {max_length} 个字符"
            else:
                setattr(setting, field, value)
                changed[field] = value
        for field, (minimum, maximum, label) in number_fields.items():
            if field not in request.data:
                continue
            try:
                value = int(request.data[field])
            except (TypeError, ValueError):
                errors[field] = f"{label}必须为整数"
                continue
            if not minimum <= value <= maximum:
                errors[field] = f"{label}必须在 {minimum}–{maximum} 之间"
            else:
                setattr(setting, field, value)
                changed[field] = value
        if errors:
            raise ValidationError(errors)
        if changed:
            setting.save(update_fields=[*changed, "updated_at"])
            AuditLog.objects.create(
                actor=request.user,
                action="UPDATE",
                resource_type="SystemSetting",
                resource_id=str(setting.pk),
                detail={"fields": list(changed)},
                request_id=getattr(request, "request_id", ""),
                source_ip=request.META.get("REMOTE_ADDR"),
            )
    return Response(
        {
            "brand_logo_text": setting.brand_logo_text,
            "home_page_title": setting.home_page_title,
            "browser_title": setting.browser_title,
            "login_page_description": setting.login_page_description,
            "monitor_wall_title": setting.monitor_wall_title,
            "dashboard_refresh_seconds": setting.dashboard_refresh_seconds,
            "monitor_wall_refresh_seconds": setting.monitor_wall_refresh_seconds,
            "monitor_result_retention_count": setting.monitor_result_retention_count,
            "updated_at": setting.updated_at,
            "can_manage": "system.manage" in user_permissions(request.user),
        }
    )


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
@permission_classes([AllowAny])
def public_branding(request):
    setting = SystemSetting.load()
    return Response(
        {
            "brand_logo_text": setting.brand_logo_text,
            "home_page_title": setting.home_page_title,
            "browser_title": setting.browser_title,
            "login_page_description": setting.login_page_description,
        }
    )


class MonitorViewSet(BaseViewSet):
    queryset = Monitor.objects.select_related("business", "state", "state__last_result").all()
    serializer_class = MonitorSerializer
    search_fields = ("name", "target", "business__name")
    filterset_fields = ("business", "monitor_type", "is_enabled", "is_archived", "tags")

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.query_params.get("include_archived") == "true":
            return queryset
        return queryset.filter(is_archived=False)

    def perform_destroy(self, instance):
        AuditLog.objects.create(
            actor=self.request.user,
            action="ARCHIVE",
            resource_type="Monitor",
            resource_id=str(instance.pk),
            detail={"name": instance.name},
            request_id=getattr(self.request, "request_id", ""),
            source_ip=self.request.META.get("REMOTE_ADDR"),
        )
        instance.is_enabled = False
        instance.is_archived = True
        instance.save(update_fields=["is_enabled", "is_archived", "updated_at"])
        now = timezone.now()
        for incident in instance.incidents.filter(status__in=["NEW", "ACKNOWLEDGED", "PROCESSING"]):
            incident.status = "CLOSED"
            incident.closed_at = now
            incident.resolution = "探测任务已删除，事件自动关闭"
            incident.save(update_fields=["status", "closed_at", "resolution"])
            IncidentTimeline.objects.create(
                incident=incident,
                actor=self.request.user,
                action="CLOSED",
                payload={"resolution": incident.resolution, "reason": "MONITOR_ARCHIVED"},
            )

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        monitor = self.get_object()
        result = execute_and_record(monitor)
        return Response(MonitorResultSerializer(result).data)

    @action(detail=False, methods=["post"], url_path="test-all")
    def test_all(self, request):
        monitors = self.get_queryset().filter(
            is_enabled=True, business__is_enabled=True, business__is_archived=False
        )
        results = []
        for monitor in monitors:
            result = execute_and_record(monitor)
            results.append(
                {
                    "id": str(monitor.id),
                    "business": monitor.business.name,
                    "monitor": monitor.name,
                    "type": monitor.monitor_type,
                    "target": monitor.target,
                    **MonitorResultSerializer(result).data,
                }
            )
        passed = sum(1 for item in results if item["success"])
        return Response(
            {
                "success": passed == len(results) and bool(results),
                "total": len(results),
                "passed": passed,
                "failed": len(results) - passed,
                "results": results,
            }
        )

    @action(detail=False, methods=["post"], url_path="bulk-enable")
    def bulk_enable(self, request):
        ids, enabled = request.data.get("ids", []), bool(request.data.get("enabled", True))
        updated = (
            self.get_queryset()
            .filter(id__in=ids)
            .update(is_enabled=enabled, next_run_at=timezone.now())
        )
        return Response({"updated": updated})

    @action(detail=True, methods=["get"])
    def results(self, request, pk=None):
        qs = self.get_object().results.order_by("-checked_at")[:500]
        return Response(MonitorResultSerializer(qs, many=True).data)

    @action(detail=True, methods=["get"])
    def metrics(self, request, pk=None):
        hours = min(int(request.query_params.get("hours", 24)), 24 * 90)
        qs = (
            self.get_object()
            .results.filter(checked_at__gte=timezone.now() - timedelta(hours=hours))
            .order_by("checked_at")
        )
        return Response(
            [
                {"checked_at": r.checked_at, "success": r.success, "latency_ms": r.latency_ms}
                for r in qs
            ]
        )


class IncidentViewSet(BaseViewSet):
    queryset = Incident.objects.select_related("monitor", "monitor__business").all()
    serializer_class = IncidentSerializer
    filterset_fields = ("status", "severity", "monitor")
    search_fields = ("number", "title", "summary")

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        incident = self.get_object()
        if incident.status == "NEW":
            incident.status, incident.acknowledged_at = "ACKNOWLEDGED", timezone.now()
            incident.save(update_fields=["status", "acknowledged_at"])
            IncidentTimeline.objects.create(
                incident=incident, action="ACKNOWLEDGED", actor=request.user
            )
        return Response(self.get_serializer(incident).data)

    @action(detail=True, methods=["post"])
    def process(self, request, pk=None):
        incident = self.get_object()
        if incident.status not in ("NEW", "ACKNOWLEDGED"):
            raise ValidationError({"status": "只有新建或已确认事件可以转为处理中"})
        incident.status = "PROCESSING"
        incident.assignee = request.user
        incident.save(update_fields=["status", "assignee"])
        IncidentTimeline.objects.create(
            incident=incident,
            action="PROCESSING",
            actor=request.user,
            payload={"comment": request.data.get("comment", "")},
        )
        return Response(self.get_serializer(incident).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        incident = self.get_object()
        resolution = str(request.data.get("resolution", "")).strip()
        if not resolution:
            raise ValidationError({"resolution": "关闭事件时必须填写解决说明"})
        if incident.status == "CLOSED":
            raise ValidationError({"status": "事件已关闭"})
        incident.status = "CLOSED"
        incident.closed_at = timezone.now()
        incident.resolution = resolution
        incident.root_cause = request.data.get("root_cause", incident.root_cause)
        incident.save()
        IncidentTimeline.objects.create(
            incident=incident,
            action="CLOSED",
            actor=request.user,
            payload={"resolution": resolution},
        )
        return Response(self.get_serializer(incident).data)


class AlertRuleViewSet(BaseViewSet):
    queryset = AlertRule.objects.prefetch_related("monitors", "channels").all()
    serializer_class = AlertRuleSerializer
    search_fields = ("name",)
    filterset_fields = ("severity", "is_enabled", "monitors", "channels")

    @action(detail=True, methods=["post"])
    def toggle(self, request, pk=None):
        rule = self.get_object()
        rule.is_enabled = bool(request.data.get("enabled", not rule.is_enabled))
        rule.save(update_fields=["is_enabled"])
        return Response(self.get_serializer(rule).data)


class NotificationLogViewSet(ReadOnlyBaseViewSet):
    queryset = NotificationLog.objects.select_related("incident", "channel").all()
    serializer_class = NotificationLogSerializer
    search_fields = (
        "incident__number",
        "incident__title",
        "channel__name",
        "recipient_key",
        "error_summary",
    )
    filterset_fields = ("incident", "phase", "channel", "status")
    ordering = ("-created_at",)

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        log = self.get_object()
        if not log.channel.is_enabled:
            raise ValidationError({"channel": "通知渠道已停用，无法重试"})
        result = send_notification(
            log.channel,
            f"[{log.incident.severity}] {log.incident.title}",
            log.incident.summary or f"事件编号：{log.incident.number}",
        )
        log.attempts += 1
        log.status = "SENT" if result["success"] else "FAILED"
        log.error_summary = "" if result["success"] else result["message"]
        log.sent_at = timezone.now() if result["success"] else None
        log.save(update_fields=["attempts", "status", "error_summary", "sent_at"])
        return Response(
            {**self.get_serializer(log).data, "delivery": result},
            status=200 if result["success"] else 400,
        )


class NotificationChannelViewSet(BaseViewSet):
    queryset = NotificationChannel.objects.all()
    serializer_class = NotificationChannelSerializer
    search_fields = ("name",)
    filterset_fields = ("channel_type", "is_enabled")

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        channel = self.get_object()
        if not channel.is_enabled:
            return Response({"success": False, "message": "渠道未启用"}, status=400)
        result = send_test_notification(channel)
        return Response(result, status=200 if result["success"] else 400)

    @action(detail=False, methods=["post"], url_path="test-all")
    def test_all(self, request):
        results = []
        for channel in self.get_queryset():
            result = (
                send_test_notification(channel)
                if channel.is_enabled
                else {"success": False, "message": "渠道未启用", "latency_ms": 0, "detail": {}}
            )
            results.append(
                {
                    "id": str(channel.id),
                    "name": channel.name,
                    "type": channel.channel_type,
                    **result,
                }
            )
        passed = sum(1 for item in results if item["success"])
        return Response(
            {
                "success": passed == len(results) and bool(results),
                "total": len(results),
                "passed": passed,
                "failed": len(results) - passed,
                "results": results,
            }
        )


class StatusPageViewSet(BaseViewSet):
    queryset = StatusPage.objects.prefetch_related("businesses", "monitors").all()
    serializer_class = StatusPageSerializer
    search_fields = ("name", "slug")
    filterset_fields = ("access_mode", "is_enabled")

    @action(detail=True, methods=["post"], url_path="rotate-token")
    def rotate_token(self, request, pk=None):
        page = self.get_object()
        token = secrets.token_urlsafe(32)
        page.token_hash = hashlib.sha256(token.encode()).hexdigest()
        page.save(update_fields=["token_hash"])
        AuditLog.objects.create(
            actor=request.user,
            action="ROTATE_TOKEN",
            resource_type="StatusPage",
            resource_id=str(page.pk),
            request_id=getattr(request, "request_id", ""),
            source_ip=request.META.get("REMOTE_ADDR"),
        )
        return Response({"token": token})


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    since_24h = timezone.now() - timedelta(hours=24)
    probe_stats = MonitorResult.objects.filter(
        checked_at__gte=since_24h, monitor__is_archived=False
    ).aggregate(
        total=Count("id"),
        passed=Count("id", filter=Q(success=True)),
        failed=Count("id", filter=Q(success=False)),
        average_latency_ms=Avg("latency_ms", filter=Q(success=True)),
    )
    monitors = list(
        Monitor.objects.select_related("business", "state", "state__last_result")
        .filter(is_archived=False)
        .order_by("business__level", "name")
    )
    latest_monitors = []
    counts = {
        status: 0
        for status in ("UP", "DOWN", "DEGRADED", "MAINTENANCE", "PAUSED", "PENDING", "UNKNOWN")
    }
    for monitor in monitors:
        state = getattr(monitor, "state", None)
        result = getattr(state, "last_result", None)
        status = "PAUSED" if not monitor.is_enabled else getattr(state, "status", "PENDING")
        if result is not None and not result.success and status not in ("DOWN", "MAINTENANCE"):
            status = "DEGRADED"
        counts[status] += 1
        latest_monitors.append(
            {
                "id": str(monitor.id),
                "name": monitor.name,
                "business": monitor.business.name,
                "type": monitor.monitor_type,
                "status": status,
                "available": result.success if result is not None and monitor.is_enabled else None,
                "last_checked_at": result.checked_at if result else None,
                "latency_ms": result.latency_ms if result else None,
                "error_summary": result.error_summary if result and not result.success else "",
            }
        )
    health_denominator = sum(
        counts[status] for status in ("UP", "DOWN", "DEGRADED", "PENDING", "UNKNOWN")
    )
    return Response(
        {
            "snapshot_at": timezone.now(),
            "businesses_total": BusinessSystem.objects.filter(is_archived=False).count(),
            "monitors_total": Monitor.objects.filter(is_archived=False).count(),
            "states": counts,
            "health_rate": round(counts["UP"] / health_denominator * 100, 2)
            if health_denominator
            else None,
            "open_incidents": Incident.objects.filter(
                status__in=["NEW", "ACKNOWLEDGED", "PROCESSING"],
                monitor__is_archived=False,
            ).count(),
            "today_incidents": Incident.objects.filter(
                opened_at__date=timezone.localdate(), monitor__is_archived=False
            ).count(),
            "probe_stats_24h": {
                **probe_stats,
                "success_rate": round(probe_stats["passed"] / probe_stats["total"] * 100, 2)
                if probe_stats["total"]
                else None,
            },
            "average_latency_ms": probe_stats["average_latency_ms"],
            "recent_incidents": [
                {
                    "id": str(i.id),
                    "number": i.number,
                    "title": i.title,
                    "severity": i.severity,
                    "status": i.status,
                    "monitor": i.monitor.name,
                    "business": i.monitor.business.name,
                    "opened_at": i.opened_at,
                }
                for i in Incident.objects.select_related("monitor", "monitor__business")
                .filter(monitor__is_archived=False)
                .exclude(status__in=["CLOSED", "RECOVERED"])
                .order_by("-opened_at")[:6]
            ],
            "latest_monitors": latest_monitors,
        }
    )


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def sla_report(request):
    try:
        days = max(1, min(int(request.query_params.get("days", 30)), 365))
    except (TypeError, ValueError) as exc:
        raise ValidationError({"days": "统计周期必须为 1 到 365 天"}) from exc
    since = timezone.now() - timedelta(days=days)
    data = []
    monitors = Monitor.objects.select_related("business").filter(is_archived=False)
    if business_id := request.query_params.get("business"):
        monitors = monitors.filter(business_id=business_id)
    total_samples = included_samples = passed_samples = 0
    for monitor in monitors:
        qs = monitor.results.filter(checked_at__gte=since)
        total_before_exclusion = qs.count()
        windows = (
            MaintenanceWindow.objects.filter(
                is_enabled=True, exclude_from_sla=True, end_at__gte=since
            )
            .filter(Q(monitors=monitor) | Q(businesses=monitor.business))
            .distinct()
        )
        exclusion = Q()
        for window in windows:
            exclusion |= Q(checked_at__gte=window.start_at, checked_at__lte=window.end_at)
        if exclusion:
            qs = qs.exclude(exclusion)
        total = qs.count()
        up = qs.filter(success=True).count()
        total_samples += total_before_exclusion
        included_samples += total
        passed_samples += up
        data.append(
            {
                "monitor_id": monitor.id,
                "monitor_name": monitor.name,
                "business_name": monitor.business.name,
                "availability": round(up / total * 100, 4) if total else None,
                "samples": total,
                "excluded_samples": total_before_exclusion - total,
                "average_latency_ms": qs.filter(success=True).aggregate(v=Avg("latency_ms"))["v"],
                "sla_target": monitor.business.sla_target,
                "target_met": (up / total * 100) >= float(monitor.business.sla_target)
                if total
                else None,
            }
        )
    return Response(
        {
            "period_days": days,
            "generated_at": timezone.now(),
            "formula": "成功样本数 /（总样本数 - SLA 排除维护期样本数）× 100%",
            "summary": {
                "monitors": len(data),
                "total_samples": total_samples,
                "included_samples": included_samples,
                "excluded_samples": total_samples - included_samples,
                "availability": round(passed_samples / included_samples * 100, 4)
                if included_samples
                else None,
                "targets_met": sum(1 for row in data if row["target_met"] is True),
            },
            "results": data,
        }
    )


@extend_schema(responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT})
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([AnonRateThrottle])
def public_status(request, slug):
    page = StatusPage.objects.filter(slug=slug, is_enabled=True).first()
    if not page:
        return Response({"detail": "状态页不存在"}, status=404)
    if page.access_mode == "TOKEN" and not secrets.compare_digest(
        page.token_hash, hashlib.sha256(request.query_params.get("token", "").encode()).hexdigest()
    ):
        return Response({"detail": "访问令牌无效"}, status=403)
    monitors = (
        Monitor.objects.select_related("state", "state__last_result", "business")
        .filter(
            Q(id__in=page.monitors.values("id")) | Q(business__in=page.businesses.all()),
            is_archived=False,
        )
        .distinct()
        .order_by("business__name", "name")
    )
    monitor_rows = []
    for monitor in monitors:
        state = getattr(monitor, "state", None)
        result = getattr(state, "last_result", None)
        monitor_rows.append(
            {
                "id": monitor.id,
                "name": monitor.name,
                "business": monitor.business.name,
                "type": monitor.monitor_type,
                "status": "PAUSED"
                if not monitor.is_enabled
                else getattr(state, "status", "UNKNOWN"),
                "last_checked_at": result.checked_at if result else None,
                "latency_ms": result.latency_ms if result else None,
            }
        )
    failing = sum(1 for row in monitor_rows if row["status"] in ("DOWN", "DEGRADED"))
    return Response(
        {
            "name": page.name,
            "description": page.description,
            "theme_color": page.theme_color,
            "updated_at": timezone.now(),
            "overall_status": "DOWN"
            if any(row["status"] == "DOWN" for row in monitor_rows)
            else "DEGRADED"
            if failing
            else "UP",
            "summary": {"total": len(monitor_rows), "affected": failing},
            "monitors": monitor_rows,
        }
    )


@extend_schema(responses={200: OpenApiTypes.BINARY})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def sla_export(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="sla.csv"'
    writer = csv.writer(response)
    report = sla_report(request).data
    writer.writerow(
        [
            "业务",
            "监控项",
            "SLA目标(%)",
            "实际可用率(%)",
            "是否达标",
            "纳入样本",
            "排除维护样本",
            "平均响应(ms)",
        ]
    )
    for row in report["results"]:
        writer.writerow(
            [
                row["business_name"],
                row["monitor_name"],
                row["sla_target"],
                row["availability"] if row["availability"] is not None else "",
                "是" if row["target_met"] else "否" if row["target_met"] is False else "无数据",
                row["samples"],
                row["excluded_samples"],
                row["average_latency_ms"] or "",
            ]
        )
    return response
