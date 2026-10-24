import re
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import Department, Role, UserProfile
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
    MonitorState,
)
from apps.status_pages.models import StatusPage

from .iam import SYSTEM_ROLES, guard_role, guard_user, role_permissions
from .monitor_config import DATABASE_TYPES, SECRET_HEADERS, validate_config
from .permissions import VALID_PERMISSIONS
from .secrets import encrypt_secret


class BaseSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        if "timeout_seconds" in attrs or "interval_seconds" in attrs:
            timeout = attrs.get("timeout_seconds", getattr(self.instance, "timeout_seconds", None))
            interval = attrs.get(
                "interval_seconds", getattr(self.instance, "interval_seconds", None)
            )
            if timeout is not None and interval is not None and timeout >= interval:
                raise serializers.ValidationError({"timeout_seconds": "必须小于探测周期"})
        return attrs


def serializer_for(model, fields="__all__", read_only=()):
    meta = type("Meta", (), {"model": model, "fields": fields, "read_only_fields": read_only})
    return type(f"{model.__name__}Serializer", (BaseSerializer,), {"Meta": meta})


UserProfileSerializer = serializer_for(UserProfile)


class DepartmentSerializer(BaseSerializer):
    parent_name = serializers.CharField(source="parent.name", read_only=True)
    user_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Department
        fields = "__all__"

    def validate(self, attrs):
        attrs = super().validate(attrs)
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        node, seen = parent, set()
        while node:
            if node.pk in seen or (self.instance and node.pk == self.instance.pk):
                raise serializers.ValidationError({"parent": "上级部门不能形成循环"})
            seen.add(node.pk)
            node = node.parent
        duplicate = Department.objects.filter(
            parent=parent, name=attrs.get("name", getattr(self.instance, "name", ""))
        )
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError({"name": "同一上级下已存在同名部门"})
        return attrs


class RoleSerializer(BaseSerializer):
    is_system_role = serializers.SerializerMethodField()
    effective_permissions = serializers.SerializerMethodField()

    def get_is_system_role(self, obj) -> bool:
        return obj.code in SYSTEM_ROLES

    def get_effective_permissions(self, obj) -> list[str]:
        return sorted(role_permissions(obj))

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request")
        guard_role(getattr(request, "user", None), self.instance, attrs)
        return attrs

    user_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Role
        fields = "__all__"
        read_only_fields = ("data_scope",)

    def validate_permissions(self, value):
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise serializers.ValidationError("权限必须为列表")
        invalid = set(value) - VALID_PERMISSIONS
        if invalid:
            raise serializers.ValidationError(f"包含无效权限：{', '.join(sorted(invalid))}")
        return sorted(set(value))


class UserSerializer(BaseSerializer):
    password = serializers.CharField(
        write_only=True,
        required=False,
        min_length=12,
        trim_whitespace=False,
        error_messages={"min_length": "用户密码至少为12位"},
    )
    roles = serializers.PrimaryKeyRelatedField(
        source="business_roles", queryset=Role.objects.all(), many=True, required=False
    )
    department = serializers.PrimaryKeyRelatedField(
        source="profile.department",
        queryset=Department.objects.all(),
        required=False,
        allow_null=True,
    )
    department_name = serializers.CharField(source="profile.department.name", read_only=True)
    phone = serializers.CharField(source="profile.phone", required=False, allow_blank=True)
    data_scope = serializers.ChoiceField(
        source="profile.data_scope", choices=["ALL", "DEPARTMENT", "SELF"], read_only=True
    )

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "password",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "is_superuser",
            "date_joined",
            "roles",
            "department",
            "department_name",
            "phone",
            "data_scope",
        )
        read_only_fields = ("date_joined", "is_superuser")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request")
        guard_user(getattr(request, "user", None), self.instance, attrs)
        department = attrs.get("profile", {}).get("department")
        old_department = getattr(getattr(self.instance, "profile", None), "department_id", None)
        if department and not department.is_enabled and department.pk != old_department:
            raise serializers.ValidationError({"department": "不能新分配到停用部门"})
        old_roles = (
            set(self.instance.business_roles.values_list("pk", flat=True))
            if self.instance
            else set()
        )
        if any(
            not role.is_enabled and role.pk not in old_roles
            for role in attrs.get("business_roles", [])
        ):
            raise serializers.ValidationError({"roles": "不能新分配已停用角色"})
        password = attrs.get("password")
        if self.instance is None and not password:
            raise serializers.ValidationError({"password": "创建账号必须设置初始密码"})
        if password:
            try:
                candidate = User(
                    username=attrs.get("username", getattr(self.instance, "username", "")),
                    email=attrs.get("email", getattr(self.instance, "email", "")),
                )
                validate_password(password, candidate)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Accounts created outside this API may not have a UserProfile yet.
        # Always expose a valid default so an edit can be submitted unchanged.
        if not data.get("data_scope"):
            data["data_scope"] = "SELF"
        return data

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password", None)
        roles = validated_data.pop("business_roles", [])
        profile = validated_data.pop("profile", {})
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        user.business_roles.set(roles)
        UserProfile.objects.create(user=user, **profile)
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        profile = validated_data.pop("profile", {})
        instance = super().update(instance, validated_data)
        user_profile, _ = UserProfile.objects.get_or_create(user=instance)
        for key, value in profile.items():
            setattr(user_profile, key, value)
        if profile:
            user_profile.save()
        if password:
            instance.set_password(password)
            instance.save(update_fields=["password"])
        return instance


class BusinessGroupSerializer(BaseSerializer):
    parent_name = serializers.CharField(source="parent.name", read_only=True, default="")

    class Meta:
        model = BusinessGroup
        fields = "__all__"
        validators = []

    def validate(self, attrs):
        attrs = super().validate(attrs)
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        seen = set()
        node = parent
        while node:
            if node.pk in seen or (self.instance and node.pk == self.instance.pk):
                raise serializers.ValidationError(
                    {"parent": "父级不能是自身或下级分组，不能形成循环"}
                )
            seen.add(node.pk)
            node = node.parent
        name = attrs.get("name", getattr(self.instance, "name", ""))
        duplicates = BusinessGroup.objects.filter(parent=parent, name=name)
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError({"name": "同一父级下已存在同名业务分组"})
        return attrs


class TagSerializer(BaseSerializer):
    class Meta:
        model = Tag
        fields = "__all__"

    def validate_color(self, value):
        if not re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", value):
            raise serializers.ValidationError("请输入十六进制颜色，如 #409EFF")
        return value.upper()


class BusinessSystemSerializer(BaseSerializer):
    sla_target = serializers.DecimalField(
        max_digits=6, decimal_places=3, min_value=0, max_value=100, required=False
    )
    group_name = serializers.CharField(source="group.name", read_only=True, default="")
    department_name = serializers.CharField(source="department.name", read_only=True, default="")
    owner_name = serializers.CharField(source="owner.username", read_only=True, default="")
    tag_names = serializers.SerializerMethodField()
    monitor_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = BusinessSystem
        fields = "__all__"

    def get_tag_names(self, obj) -> str:
        return "、".join(tag.name for tag in obj.tags.all())

    def validate_service_schedule(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("服务时间元数据必须是对象")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        archived = attrs.get("is_archived", getattr(self.instance, "is_archived", False))
        if archived:
            attrs["is_enabled"] = False
        return attrs


class MonitorSerializer(BaseSerializer):
    secret_mask = "********"
    business_name = serializers.CharField(source="business.name", read_only=True)
    current_status = serializers.SerializerMethodField()
    service_available = serializers.SerializerMethodField()
    last_checked_at = serializers.SerializerMethodField()
    last_latency_ms = serializers.SerializerMethodField()
    last_error = serializers.SerializerMethodField()

    def _state_and_result(self, obj):
        state = getattr(obj, "state", None)
        return state, getattr(state, "last_result", None)

    def get_current_status(self, obj) -> str:
        if not obj.is_enabled or not obj.business.is_enabled or obj.business.is_archived:
            return "PAUSED"
        state, result = self._state_and_result(obj)
        status = getattr(state, "status", "PENDING")
        if (
            result is not None
            and not result.success
            and status not in ("DOWN", "MAINTENANCE", "PENDING", "PAUSED")
        ):
            return "DEGRADED"
        return status

    def get_service_available(self, obj) -> bool | None:
        if not obj.is_enabled or not obj.business.is_enabled or obj.business.is_archived:
            return None
        state, result = self._state_and_result(obj)
        if state and state.status == "PENDING":
            return None
        return result.success if result is not None else None

    def get_last_checked_at(self, obj) -> datetime | None:
        _, result = self._state_and_result(obj)
        return result.checked_at if result else None

    def get_last_latency_ms(self, obj) -> float | None:
        _, result = self._state_and_result(obj)
        return result.latency_ms if result else None

    def get_last_error(self, obj) -> str:
        _, result = self._state_and_result(obj)
        return result.error_summary if result and not result.success else ""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if set(attrs) == {"is_enabled"} and attrs["is_enabled"] is False:
            return attrs
        kind = attrs.get("monitor_type", getattr(self.instance, "monitor_type", None))
        target = str(attrs.get("target", getattr(self.instance, "target", ""))).strip()
        config = deepcopy(attrs.get("config", getattr(self.instance, "config", {})))
        if not isinstance(config, dict) or not isinstance(config.get("auth", {}), dict):
            raise serializers.ValidationError({"config": "配置和 auth 必须是 JSON 对象"})
        limits = {
            "interval_seconds": (5, 86400, 60),
            "timeout_seconds": (1, 30, 10),
            "failure_threshold": (1, 100, 3),
            "recovery_threshold": (1, 100, 2),
        }
        for field, (low, high, default) in limits.items():
            value = attrs.get(field, getattr(self.instance, field, default))
            if not low <= value <= high:
                raise serializers.ValidationError({field: f"必须在 {low} 到 {high} 之间"})
        timeout = attrs.get("timeout_seconds", getattr(self.instance, "timeout_seconds", 10))
        interval = attrs.get("interval_seconds", getattr(self.instance, "interval_seconds", 60))
        if timeout >= interval:
            raise serializers.ValidationError({"timeout_seconds": "必须小于探测周期"})
        old = getattr(self.instance, "config", {}) or {}
        auth = config.get("auth", {})
        for key in ("token", "password", "value", "client_secret"):
            if auth.get(key) == self.secret_mask:
                auth[key] = (old.get("auth") or {}).get(key, "")
        if config.get("password") == self.secret_mask:
            config["password"] = old.get("password", "")
        for key, value in (
            (config.get("headers") or {}).items()
            if isinstance(config.get("headers", {}), dict)
            else []
        ):
            if key.lower() in SECRET_HEADERS and value == self.secret_mask:
                config["headers"][key] = next(
                    (v for k, v in old.get("headers", {}).items() if k.lower() == key.lower()), ""
                )
        try:
            config = validate_config(kind, target, config)
        except (ValueError, TypeError) as exc:
            raise serializers.ValidationError({"config": str(exc)}) from exc
        auth = config.get("auth", {})
        for key in ("token", "password", "value", "client_secret"):
            if auth.get(key):
                auth[key] = encrypt_secret(auth[key])
        for key, value in (config.get("headers") or {}).items():
            if key.lower() in SECRET_HEADERS and value:
                config["headers"][key] = encrypt_secret(value)
        if kind in DATABASE_TYPES and config.get("password"):
            config["password"] = encrypt_secret(config["password"])
        attrs["config"], attrs["target"] = config, target
        return attrs

    def update(self, instance, validated_data):
        original = {
            "name": instance.name,
            "monitor_type": instance.monitor_type,
            "target": instance.target,
            "business_id": str(instance.business_id),
            "business_name": instance.business.name,
        }
        spec_changed = any(
            key in validated_data and validated_data[key] != getattr(instance, key)
            for key in (
                "monitor_type",
                "target",
                "config",
                "business",
                "interval_seconds",
                "timeout_seconds",
                "failure_threshold",
                "recovery_threshold",
                "warning_latency_ms",
            )
        )
        if spec_changed or ("name" in validated_data and validated_data["name"] != instance.name):
            instance.results.filter(monitor_snapshot={}).update(monitor_snapshot=original)
        enabled_changed = (
            "is_enabled" in validated_data and validated_data["is_enabled"] != instance.is_enabled
        )
        instance = super().update(instance, validated_data)
        if enabled_changed or spec_changed:
            instance.next_run_at = timezone.now()
            instance.save(update_fields=["next_run_at"])
            instance._state.fields_cache.pop("state", None)
            MonitorState.objects.filter(monitor=instance).update(
                status="PENDING" if instance.is_enabled else "PAUSED",
                consecutive_failures=0,
                consecutive_successes=0,
            )
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        config = deepcopy(data.get("config", {}))
        if not isinstance(config, dict):
            config = {}
        if not isinstance(config.get("auth", {}), dict):
            config["auth"] = {}
        if not isinstance(config.get("headers", {}), dict):
            config["headers"] = {}
        data["config"] = config
        for key in ("token", "password", "value", "client_secret"):
            if config.get("auth", {}).get(key):
                config["auth"][key] = self.secret_mask
        for key in config.get("headers", {}):
            if key.lower() in SECRET_HEADERS and config["headers"][key]:
                config["headers"][key] = self.secret_mask
        if data.get("monitor_type") in DATABASE_TYPES and config.get("password"):
            config["password"] = self.secret_mask
        return data

    class Meta:
        model = Monitor
        fields = "__all__"
        read_only_fields = ("next_run_at", "is_archived", "created_at", "updated_at")
        extra_kwargs = {
            "config": {
                "help_text": (
                    "按探测类型配置；HTTP/API 支持认证、json/form/body、JSONPath断言；"
                    "PING支持丢包阈值；SSL支持warn/fail预警。详见 docs/monitor-options.md。"
                )
            }
        }


class MonitorResultSerializer(BaseSerializer):
    monitor_name = serializers.SerializerMethodField()
    monitor_type = serializers.SerializerMethodField()
    monitor_target = serializers.SerializerMethodField()
    business_name = serializers.SerializerMethodField()

    def get_monitor_name(self, obj) -> str:
        return obj.monitor_snapshot.get("name", obj.monitor.name)

    def get_monitor_type(self, obj) -> str:
        return obj.monitor_snapshot.get("monitor_type", obj.monitor.monitor_type)

    def get_monitor_target(self, obj) -> str:
        return obj.monitor_snapshot.get("target", obj.monitor.target)

    def get_business_name(self, obj) -> str:
        return obj.monitor_snapshot.get("business_name", obj.monitor.business.name)

    class Meta:
        model = MonitorResult
        fields = "__all__"
        read_only_fields = (
            "execution_key",
            "scheduled_at",
            "started_at",
            "checked_at",
            "finished_at",
        )


MonitorStateSerializer = serializer_for(MonitorState)
BusinessChainSerializer = serializer_for(BusinessChain)


class ChainNodeSerializer(BaseSerializer):
    class Meta:
        model = ChainNode
        fields = "__all__"

    def validate(self, attrs):
        attrs = super().validate(attrs)
        monitor = attrs.get("monitor", getattr(self.instance, "monitor", None))
        if monitor and monitor.is_archived:
            raise serializers.ValidationError({"monitor": "不能关联已删除的探测任务"})
        chain = attrs.get("chain", getattr(self.instance, "chain", None))
        if (
            self.instance
            and chain != self.instance.chain
            and (self.instance.in_edges.exists() or self.instance.out_edges.exists())
        ):
            raise serializers.ValidationError({"chain": "节点仍有关联连线，请先移除连线再变更链路"})
        return attrs


class ChainEdgeSerializer(BaseSerializer):
    class Meta:
        model = ChainEdge
        fields = "__all__"

    def validate(self, attrs):
        attrs = super().validate(attrs)
        chain = attrs.get("chain", getattr(self.instance, "chain", None))
        source = attrs.get("source", getattr(self.instance, "source", None))
        target = attrs.get("target", getattr(self.instance, "target", None))
        if not all((chain, source, target)):
            return attrs
        if source.chain_id != chain.pk or target.chain_id != chain.pk:
            raise serializers.ValidationError("连线两端必须属于当前业务链路")
        if source.pk == target.pk:
            raise serializers.ValidationError("节点不能连接自身")
        edges = ChainEdge.objects.filter(chain=chain)
        if self.instance:
            edges = edges.exclude(pk=self.instance.pk)
        graph = {}
        for left, right in edges.values_list("source_id", "target_id"):
            graph.setdefault(left, []).append(right)
        pending, seen = [target.pk], set()
        while pending:
            node = pending.pop()
            if node == source.pk:
                raise serializers.ValidationError("连线将形成循环依赖")
            if node not in seen:
                seen.add(node)
                pending.extend(graph.get(node, []))
        return attrs


IncidentTimelineSerializer = serializer_for(IncidentTimeline)


class IncidentSerializer(BaseSerializer):
    monitor_name = serializers.CharField(source="monitor.name", read_only=True)
    business_name = serializers.CharField(source="monitor.business.name", read_only=True)
    assignee_name = serializers.CharField(source="assignee.username", read_only=True)
    timeline = IncidentTimelineSerializer(many=True, read_only=True)

    class Meta:
        model = Incident
        fields = "__all__"
        read_only_fields = (
            "number",
            "monitor",
            "status",
            "severity",
            "opened_at",
            "acknowledged_at",
            "recovered_at",
            "closed_at",
            "assignee",
            "resolution",
            "root_cause",
        )


class AlertRuleSerializer(BaseSerializer):
    severity = serializers.ChoiceField(choices=("CRITICAL", "HIGH", "MEDIUM", "LOW"))

    def validate(self, attrs):
        attrs = super().validate(attrs)
        repeat = attrs.get(
            "repeat_interval_minutes",
            getattr(self.instance, "repeat_interval_minutes", 30),
        )
        escalation = attrs.get(
            "escalation_minutes", getattr(self.instance, "escalation_minutes", 60)
        )
        if repeat < 1:
            raise serializers.ValidationError({"repeat_interval_minutes": "重复间隔至少为 1 分钟"})
        if escalation < repeat:
            raise serializers.ValidationError({"escalation_minutes": "升级时间不能小于重复间隔"})
        monitors = attrs.get("monitors", getattr(self.instance, "monitors", None))
        channels = attrs.get("channels", getattr(self.instance, "channels", None))
        if monitors is None or not (monitors.exists() if hasattr(monitors, "exists") else monitors):
            raise serializers.ValidationError({"monitors": "至少选择一个探测任务"})
        if channels is None or not (channels.exists() if hasattr(channels, "exists") else channels):
            raise serializers.ValidationError({"channels": "至少选择一个通知渠道"})
        return attrs

    class Meta:
        model = AlertRule
        fields = "__all__"


class NotificationChannelSerializer(BaseSerializer):
    secret_mask = "********"
    required_config = {
        "EMAIL": ("host", "from_email", "recipients"),
        "WECHAT": ("webhook_url",),
        "DINGTALK": ("webhook_url",),
        "WEBHOOK": ("url",),
        "SERVERCHAN": ("sendkey",),
    }

    class Meta:
        model = NotificationChannel
        fields = "__all__"

    def validate(self, attrs):
        attrs = super().validate(attrs)
        channel_type = attrs.get("channel_type", getattr(self.instance, "channel_type", None))
        config = attrs.get("config", getattr(self.instance, "config", {}) or {})
        if not isinstance(config, dict):
            raise serializers.ValidationError({"config": "渠道配置必须为对象"})
        config = deepcopy(config)
        old_config = getattr(self.instance, "config", {}) or {}
        for key in ("password", "secret", "sendkey"):
            if config.get(key) == self.secret_mask:
                if old_config.get(key):
                    config[key] = old_config[key]
                else:
                    config.pop(key, None)
        missing = [key for key in self.required_config.get(channel_type, ()) if not config.get(key)]
        if missing:
            raise serializers.ValidationError({"config": f"缺少必填参数：{', '.join(missing)}"})
        for key in ("use_ssl", "use_tls"):
            if key in config:
                config[key] = serializers.BooleanField().run_validation(config[key])
        if channel_type == "EMAIL" and config.get("use_ssl") and config.get("use_tls"):
            raise serializers.ValidationError({"config": "SSL 与 STARTTLS 不能同时启用"})
        if config.get("timeout") is not None:
            config["timeout"] = serializers.FloatField(min_value=1, max_value=60).run_validation(
                config["timeout"]
            )
        if config.get("port") is not None:
            config["port"] = serializers.IntegerField(min_value=1, max_value=65535).run_validation(
                config["port"]
            )
        if "headers" in config and (
            not isinstance(config["headers"], dict)
            or any(
                not isinstance(k, str) or not isinstance(v, str) or "\n" in k + v or "\r" in k + v
                for k, v in config["headers"].items()
            )
        ):
            raise serializers.ValidationError({"config": "请求头必须为字符串对象，且不能包含换行"})
        for key in ("password", "secret", "sendkey"):
            if config.get(key):
                config[key] = encrypt_secret(config[key])
        attrs["config"] = config
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["config"] = deepcopy(data.get("config") or {})
        for key in ("password", "secret", "sendkey"):
            if data.get("config", {}).get(key):
                data["config"][key] = self.secret_mask
        return data


class NotificationLogSerializer(BaseSerializer):
    incident_number = serializers.CharField(source="incident.number", read_only=True)
    incident_title = serializers.CharField(source="incident.title", read_only=True)
    channel_name = serializers.CharField(source="channel.name", read_only=True)
    channel_type = serializers.CharField(source="channel.channel_type", read_only=True)

    class Meta:
        model = NotificationLog
        fields = "__all__"


class MaintenanceWindowSerializer(BaseSerializer):
    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise serializers.ValidationError("请输入有效的 IANA 时区，如 Asia/Shanghai") from exc
        return value

    business_names = serializers.SerializerMethodField()
    monitor_names = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    def get_business_names(self, obj) -> list[str]:
        return list(obj.businesses.values_list("name", flat=True))

    def get_monitor_names(self, obj) -> list[str]:
        return list(obj.monitors.values_list("name", flat=True))

    def get_status(self, obj) -> str:
        now = timezone.now()
        if not obj.is_enabled:
            return "DISABLED"
        if now < obj.start_at:
            return "UPCOMING"
        if now <= obj.end_at:
            return "ACTIVE"
        return "ENDED"

    def validate(self, attrs):
        attrs = super().validate(attrs)
        start = attrs.get("start_at", getattr(self.instance, "start_at", None))
        end = attrs.get("end_at", getattr(self.instance, "end_at", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"end_at": "结束时间必须晚于开始时间"})
        businesses = attrs.get("businesses", getattr(self.instance, "businesses", None))
        monitors = attrs.get("monitors", getattr(self.instance, "monitors", None))
        has_business = bool(
            businesses and (businesses.exists() if hasattr(businesses, "exists") else businesses)
        )
        has_monitor = bool(
            monitors and (monitors.exists() if hasattr(monitors, "exists") else monitors)
        )
        if not has_business and not has_monitor:
            raise serializers.ValidationError({"monitors": "至少选择一个业务系统或探测任务"})
        recurrence = attrs.get("recurrence", getattr(self.instance, "recurrence", {}) or {})
        if recurrence:
            raise serializers.ValidationError({"recurrence": "当前版本仅支持单次维护窗口，请留空"})
        return attrs

    class Meta:
        model = MaintenanceWindow
        fields = "__all__"


class StatusPageSerializer(BaseSerializer):
    def validate_theme_color(self, value):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise serializers.ValidationError("请输入六位十六进制主题色")
        return value

    business_names = serializers.SerializerMethodField()
    monitor_names = serializers.SerializerMethodField()
    monitor_count = serializers.SerializerMethodField()
    has_token = serializers.SerializerMethodField()

    def get_business_names(self, obj) -> list[str]:
        return list(obj.businesses.values_list("name", flat=True))

    def get_monitor_names(self, obj) -> list[str]:
        return list(obj.monitors.values_list("name", flat=True))

    def get_monitor_count(self, obj) -> int:
        return (
            Monitor.objects.filter(
                Q(id__in=obj.monitors.values("id")) | Q(business__in=obj.businesses.all()),
                is_archived=False,
            )
            .distinct()
            .count()
        )

    def get_has_token(self, obj) -> bool:
        return bool(obj.token_hash)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        businesses = attrs.get("businesses", getattr(self.instance, "businesses", None))
        monitors = attrs.get("monitors", getattr(self.instance, "monitors", None))
        has_business = bool(
            businesses and (businesses.exists() if hasattr(businesses, "exists") else businesses)
        )
        has_monitor = bool(
            monitors and (monitors.exists() if hasattr(monitors, "exists") else monitors)
        )
        if not has_business and not has_monitor:
            raise serializers.ValidationError({"monitors": "至少选择一个业务系统或探测任务"})
        return attrs

    class Meta:
        model = StatusPage
        exclude = ("token_hash",)


class AuditLogSerializer(BaseSerializer):
    actor_name = serializers.SerializerMethodField()

    def get_actor_name(self, obj) -> str:
        if not obj.actor:
            return "系统"
        return obj.actor.get_full_name() or obj.actor.username

    class Meta:
        model = AuditLog
        fields = "__all__"


class LoginRecordSerializer(BaseSerializer):
    user_display = serializers.SerializerMethodField()

    def get_user_display(self, obj) -> str:
        if not obj.user:
            return obj.username
        return obj.user.get_full_name() or obj.user.username

    class Meta:
        model = LoginRecord
        fields = "__all__"


class SlaQuerySerializer(serializers.Serializer):
    days = serializers.IntegerField(min_value=1, max_value=365, default=30)
    business = serializers.UUIDField(required=False)
