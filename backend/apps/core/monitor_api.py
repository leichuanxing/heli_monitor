"""Monitor workflow actions and the thirty-day historical data API."""

from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

from celery.result import AsyncResult
from django.core import signing
from django.db import transaction
from django.db.models import Avg, Count, Max, Min, Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from kombu.exceptions import OperationalError
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.monitors.models import TYPE_CHOICES, Monitor, MonitorResult

from .serializers import MonitorResultSerializer
from .tasks import execute_monitor


class MonitorIdsInput(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=100)


class MonitorEnabledInput(MonitorIdsInput):
    enabled = serializers.BooleanField()


class BatchTokenInput(serializers.Serializer):
    token = serializers.CharField(max_length=60000)


class ResultFilterInput(serializers.Serializer):
    checked_after = serializers.DateTimeField(required=False)
    checked_before = serializers.DateTimeField(required=False)
    monitor_type = serializers.ChoiceField(choices=TYPE_CHOICES, required=False)

    def validate(self, attrs):
        if (
            attrs.get("checked_after")
            and attrs.get("checked_before")
            and attrs["checked_after"] >= attrs["checked_before"]
        ):
            raise serializers.ValidationError("起止时间无效，开始时间必须早于结束时间")
        return attrs


class HistoryInput(serializers.Serializer):
    monitor = serializers.UUIDField(required=False)
    business = serializers.UUIDField(required=False)
    monitor_type = serializers.ChoiceField(choices=TYPE_CHOICES, required=False)
    checked_after = serializers.DateTimeField(required=False)
    checked_before = serializers.DateTimeField(required=False)
    search = serializers.CharField(required=False, allow_blank=True, max_length=160)
    success = serializers.BooleanField(required=False)


def selected_monitors(view, ids):
    ids = {str(value) for value in ids}
    monitors = list(view.get_queryset().filter(pk__in=ids).order_by("name"))
    if len(monitors) != len(ids):
        raise ValidationError({"ids": "部分任务不存在、已删除或不在当前范围"})
    return monitors


class MonitorActionsMixin:
    @extend_schema(request=MonitorIdsInput, responses={202: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["post"], url_path="run-batch")
    def run_batch(self, request):
        serializer = MonitorIdsInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        monitors = selected_monitors(self, serializer.validated_data["ids"])
        if any(
            not m.is_enabled or not m.business.is_enabled or m.business.is_archived
            for m in monitors
        ):
            raise ValidationError({"ids": "批量探测仅支持已启用且所属业务启用的任务"})
        now = timezone.now().isoformat()
        tasks = []
        queue_failed = False
        for monitor in monitors:
            task_id = str(uuid4())
            item = {"monitor": str(monitor.pk), "task": task_id, "name": monitor.name}
            if not queue_failed:
                try:
                    execute_monitor.apply_async(
                        args=[str(monitor.pk), now],
                        task_id=task_id,
                        expires=1800,
                        retry=False,
                    )
                except (OperationalError, ConnectionError, TimeoutError):
                    queue_failed = True
            if queue_failed:
                item["submission_failed"] = True
            tasks.append(item)
        token = signing.dumps(
            {"user": request.user.pk, "tasks": tasks, "submitted_at": now},
            salt="monitor-batch",
            compress=True,
        )
        return Response({"token": token, "total": len(tasks)}, status=202)

    @extend_schema(parameters=[BatchTokenInput], responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["get"], url_path="batch-status")
    def batch_status(self, request):
        try:
            payload = signing.loads(
                request.query_params.get("token", ""), salt="monitor-batch", max_age=7200
            )
            if payload["user"] != request.user.pk:
                raise signing.BadSignature
        except (signing.BadSignature, KeyError, TypeError) as exc:
            raise ValidationError({"token": "批次无效、已过期或不属于当前用户"}) from exc
        rows = []
        submitted_at = payload.get("submitted_at")
        expired = bool(
            submitted_at
            and timezone.now()
            > serializers.DateTimeField().to_internal_value(submitted_at) + timedelta(minutes=31)
        )
        for item in payload["tasks"]:
            if item.get("submission_failed"):
                rows.append(
                    {
                        "monitor": item["monitor"],
                        "name": item["name"],
                        "state": "FAILURE",
                        "message": "队列提交失败或状态不确定，请检查队列后重试",
                    }
                )
                continue
            task = AsyncResult(item["task"])
            row = {"monitor": item["monitor"], "name": item["name"], "state": task.state}
            if task.successful():
                if isinstance(task.result, int):
                    result = (
                        MonitorResult.objects.select_related("monitor__business")
                        .filter(pk=task.result, monitor_id=item["monitor"])
                        .first()
                    )
                    if result:
                        row.update(MonitorResultSerializer(result).data)
                    else:
                        row["state"], row["message"] = "FAILURE", "探测结果已清理"
                else:
                    row["state"], row["message"] = (
                        "SKIPPED",
                        "任务已暂停、删除或处于暂停探测的维护期",
                    )
            elif row["state"] in {"FAILURE", "REVOKED"}:
                row["message"] = "执行失败或超时，请查看系统健康状态后重试"
            elif expired:
                row["state"], row["message"] = "FAILURE", "等待执行结果已超时，请检查工作进程状态"
            rows.append(row)
        terminal = {"SUCCESS", "FAILURE", "REVOKED", "SKIPPED"}
        return Response(
            {
                "results": rows,
                "total": len(rows),
                "completed": sum(r["state"] in terminal for r in rows),
                "passed": sum(r.get("success") is True for r in rows),
                "failed": sum(
                    r.get("success") is False or r["state"] in {"FAILURE", "REVOKED"} for r in rows
                ),
                "skipped": sum(r["state"] == "SKIPPED" for r in rows),
                "done": all(r["state"] in terminal for r in rows),
            }
        )

    @extend_schema(request=None, responses={201: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["post"], url_path="copy")
    def copy_monitor(self, request, pk=None):
        source = self.get_object()
        with transaction.atomic():
            fields = {
                key: deepcopy(getattr(source, key))
                for key in (
                    "business_id",
                    "monitor_type",
                    "target",
                    "interval_seconds",
                    "timeout_seconds",
                    "failure_threshold",
                    "recovery_threshold",
                    "warning_latency_ms",
                    "config",
                )
            }
            clone = Monitor.objects.create(
                **fields, name=source.name[:150] + "（副本）", is_enabled=False
            )
            clone.tags.set(source.tags.all())
            AuditLog.objects.create(
                actor=request.user,
                action="CREATE",
                resource_type="Monitor",
                resource_id=str(clone.pk),
                detail={"copied_from": str(source.pk)},
            )
        return Response(self.get_serializer(clone).data, status=201)

    @extend_schema(
        parameters=[HistoryInput],
        responses={200: OpenApiTypes.OBJECT},
        description=(
            "series 返回完整范围的原始探测记录：id、monitor、at、latency_ms、success。"
            "按 at/id 排序，不分桶、不平均、不抽样；bucket=raw。"
            "summary 为范围统计，results 为分页明细。"
        ),
    )
    @action(detail=False, methods=["get"], url_path="history")
    def history(self, request):
        query = HistoryInput(data=dict(request.query_params.items()))
        query.is_valid(raise_exception=True)
        data = query.validated_data
        now = timezone.now()
        before = data.get("checked_before", now)
        after = data.get("checked_after", before - timedelta(days=1))
        if (
            before > now + timedelta(minutes=1)
            or after >= before
            or before - after > timedelta(days=30, seconds=1)
        ):
            raise ValidationError({"range": "请选择有效的起止时间，最长 30 天且不能晚于当前时间"})
        if after < now - timedelta(days=31):
            raise ValidationError({"range": "仅支持最近 1 个月（30 天）的历史数据"})
        qs = MonitorResult.objects.select_related("monitor__business").filter(
            monitor__is_archived=False, checked_at__gte=after, checked_at__lte=before
        )
        for field, lookup in (
            ("monitor", "monitor_id"),
            ("business", "monitor__business_id"),
            ("monitor_type", "monitor__monitor_type"),
            ("success", "success"),
        ):
            if field in data:
                if field in {"monitor_type", "business"}:
                    snapshot_key = "monitor_type" if field == "monitor_type" else "business_id"
                    qs = qs.filter(
                        Q(**{"monitor_snapshot__" + snapshot_key: str(data[field])})
                        | (Q(monitor_snapshot={}) & Q(**{lookup: data[field]}))
                    )
                else:
                    qs = qs.filter(**{lookup: data[field]})
        if data.get("search"):
            qs = qs.filter(
                Q(monitor_snapshot__name__icontains=data["search"])
                | Q(monitor_snapshot__target__icontains=data["search"])
                | Q(monitor__name__icontains=data["search"])
                | Q(monitor__business__name__icontains=data["search"])
                | Q(monitor__target__icontains=data["search"])
            )
        stats = qs.aggregate(
            total=Count("pk"),
            passed=Count("pk", filter=Q(success=True)),
            failed=Count("pk", filter=Q(success=False)),
            average_latency_ms=Avg("latency_ms"),
            min_latency_ms=Min("latency_ms"),
            max_latency_ms=Max("latency_ms"),
            first_checked_at=Min("checked_at"),
            last_checked_at=Max("checked_at"),
        )
        stats["availability"] = (
            round(stats["passed"] / stats["total"] * 100, 4) if stats["total"] else None
        )
        series = [
            {
                "id": pk,
                "monitor": str(monitor_id),
                "at": at,
                "latency_ms": latency,
                "success": success,
            }
            for pk, monitor_id, at, latency, success in qs.order_by("checked_at", "pk")
            .values_list("pk", "monitor_id", "checked_at", "latency_ms", "success")
            .iterator(chunk_size=5000)
        ]
        page = self.paginate_queryset(qs.order_by("-checked_at", "-pk"))
        response = self.get_paginated_response(MonitorResultSerializer(page, many=True).data)
        response.data.update(
            {
                "summary": stats,
                "series": series,
                "checked_after": after,
                "checked_before": before,
                "bucket": "raw",
                "retention_days": 30,
                "note": "仅统计实际保留的探测记录；空白时段不补作成功，已清理的旧数据无法恢复。",
            }
        )
        return response

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["get"], url_path="options")
    def options_list(self, request):
        from apps.businesses.models import BusinessSystem, Tag

        return Response(
            {
                "businesses": list(
                    BusinessSystem.objects.filter(is_archived=False)
                    .order_by("name")
                    .values("id", "name", "is_enabled")
                ),
                "tags": list(Tag.objects.order_by("name").values("id", "name")),
                "types": [{"value": key, "label": label} for key, label in TYPE_CHOICES],
            }
        )
