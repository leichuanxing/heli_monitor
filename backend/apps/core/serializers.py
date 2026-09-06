from copy import deepcopy
from datetime import datetime
from urllib.parse import urlparse

from django.contrib.auth.models import User
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

    def validate_parent(self, parent):
        if self.instance and parent:
            node = parent
            while node:
                if node.pk == self.instance.pk:
                    raise serializers.ValidationError("上级部门不能是自身或自身的下级部门")
                node = node.parent
        return parent


class RoleSerializer(BaseSerializer):
    user_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Role
        fields = "__all__"

    def validate_permissions(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("权限必须为列表")
        invalid = set(value) - VALID_PERMISSIONS
        if invalid:
            raise serializers.ValidationError(f"包含无效权限：{', '.join(sorted(invalid))}")
        return sorted(set(value))


class UserSerializer(BaseSerializer):
    password = serializers.CharField(
        write_only=True,
        required=False,
        min_length=8,
        error_messages={"min_length": "用户密码至少为8位"},
    )
    roles = serializers.PrimaryKeyRelatedField(
        source="business_roles", queryset=Role.objects.all(), many=True, required=False
    )
    department = serializers.PrimaryKeyRelatedField(
        source="profile.department",
        queryset=Department.objects.filter(is_enabled=True),
        required=False,
        allow_null=True,
    )
    department_name = serializers.CharField(source="profile.department.name", read_only=True)
    phone = serializers.CharField(source="profile.phone", required=False, allow_blank=True)
    data_scope = serializers.ChoiceField(
        source="profile.data_scope", choices=["ALL", "DEPARTMENT", "SELF"], required=False
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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Accounts created outside this API may not have a UserProfile yet.
        # Always expose a valid default so an edit can be submitted unchanged.
        if not data.get("data_scope"):
            data["data_scope"] = "SELF"
        return data

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


BusinessGroupSerializer = serializer_for(BusinessGroup)
TagSerializer = serializer_for(Tag)
BusinessSystemSerializer = serializer_for(BusinessSystem)


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
        if not obj.is_enabled:
            return "PAUSED"
        state, result = self._state_and_result(obj)
        status = getattr(state, "status", "PENDING")
        if result is not None and not result.success and status not in ("DOWN", "MAINTENANCE"):
            return "DEGRADED"
        return status

    def get_service_available(self, obj) -> bool | None:
        if not obj.is_enabled:
            return None
        _, result = self._state_and_result(obj)
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
        monitor_type = attrs.get("monitor_type", getattr(self.instance, "monitor_type", None))
        target = str(attrs.get("target", getattr(self.instance, "target", ""))).strip()
        config = attrs.get("config", getattr(self.instance, "config", {}) or {}) or {}
        auth = dict(config.get("auth") or {})
        old_auth = dict((getattr(self.instance, "config", {}) or {}).get("auth") or {})
        for key in ("token", "password", "value", "client_secret"):
            if auth.get(key) == self.secret_mask:
                if old_auth.get(key):
                    auth[key] = old_auth[key]
                else:
                    auth.pop(key, None)
        if auth:
            config = {**config, "auth": auth}
            attrs["config"] = config
        database_types = {"MSSQL", "POSTGRESQL", "MYSQL", "MONGODB"}
        if monitor_type in database_types and config.get("password") == self.secret_mask:
            old_password = (getattr(self.instance, "config", {}) or {}).get("password")
            config = {**config}
            if old_password:
                config["password"] = old_password
            else:
                config.pop("password", None)
            attrs["config"] = config
        if monitor_type in ("HTTP", "API"):
            parsed = urlparse(target)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise serializers.ValidationError(
                    {"target": "请输入完整 URL，例如 https://api.example.com/health"}
                )
        elif monitor_type == "TCP":
            try:
                host, port = target.rsplit(":", 1)
                valid = bool(host) and 1 <= int(port) <= 65535
            except (ValueError, TypeError):
                valid = False
            if not valid:
                raise serializers.ValidationError(
                    {"target": "请输入 主机:端口，例如 10.0.0.8:8080"}
                )
        elif monitor_type == "SSL":
            host, _, port = target.rpartition(":")
            if port and (not host or not port.isdigit() or not 1 <= int(port) <= 65535):
                raise serializers.ValidationError(
                    {"target": "请输入域名或 域名:端口，例如 example.com:443"}
                )
        elif monitor_type in ("PING", "DNS") and "://" in target:
            raise serializers.ValidationError({"target": "请输入主机名或 IP，不要包含协议前缀"})
        elif monitor_type in database_types:
            try:
                host, separator, raw_port = target.rpartition(":")
                valid = bool(target) and "://" not in target
                if separator:
                    valid = (
                        valid
                        and bool(host)
                        and raw_port.isdigit()
                        and 1 <= int(raw_port) <= 65535
                    )
            except (ValueError, TypeError):
                valid = False
            if not valid:
                raise serializers.ValidationError(
                    {"target": "请输入数据库主机或 主机:端口，不要包含连接协议"}
                )
        if not isinstance(config, dict):
            raise serializers.ValidationError({"config": "高级配置必须是 JSON 对象"})
        if monitor_type in ("HTTP", "API"):
            if config.get("headers") is not None and not isinstance(config["headers"], dict):
                raise serializers.ValidationError({"config": "headers 必须是 JSON 对象"})
            if config.get("params") is not None and not isinstance(config["params"], dict):
                raise serializers.ValidationError({"config": "params 必须是 JSON 对象"})
            body_fields = [key for key in ("json", "form", "body") if config.get(key) is not None]
            if len(body_fields) > 1:
                raise serializers.ValidationError(
                    {"config": "json、form、body 三种请求体只能配置一种"}
                )
            auth = config.get("auth") or {}
            requirements = {
                "bearer": ("token",),
                "basic": ("username", "password"),
                "api_key": ("name", "value"),
                "oauth2_client_credentials": ("token_url", "client_id", "client_secret"),
            }
            auth_type = str(auth.get("type", "none")).lower()
            if auth_type not in {"none", "", *requirements}:
                raise serializers.ValidationError({"config": f"不支持的认证类型：{auth_type}"})
            missing = [key for key in requirements.get(auth_type, ()) if not auth.get(key)]
            if missing:
                raise serializers.ValidationError(
                    {"config": f"认证配置缺少参数：{', '.join(missing)}"}
                )
        elif monitor_type in database_types:
            required = ("database", "username", "password")
            missing = [key for key in required if not config.get(key)]
            if missing:
                raise serializers.ValidationError(
                    {"config": f"数据库配置缺少参数：{', '.join(missing)}"}
                )
            query = str(config.get("query", "SELECT 1")).strip()
            if monitor_type != "MONGODB" and not query.lower().startswith(("select", "with")):
                raise serializers.ValidationError(
                    {"config": "安全起见，自定义数据库探测语句仅允许 SELECT 或 WITH 查询"}
                )
            config = {**config, "password": encrypt_secret(config["password"])}
            attrs["config"] = config
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        config = deepcopy(data.get("config", {}))
        data["config"] = config
        auth = config.get("auth", {})
        for key in ("token", "password", "value", "client_secret"):
            if auth.get(key):
                auth[key] = self.secret_mask
        if data.get("monitor_type") in {"MSSQL", "POSTGRESQL", "MYSQL", "MONGODB"}:
            if config.get("password"):
                config["password"] = self.secret_mask
        return data

    class Meta:
        model = Monitor
        fields = "__all__"


class MonitorResultSerializer(BaseSerializer):
    monitor_name = serializers.CharField(source="monitor.name", read_only=True)
    monitor_type = serializers.CharField(source="monitor.monitor_type", read_only=True)
    monitor_target = serializers.CharField(source="monitor.target", read_only=True)
    business_name = serializers.CharField(source="monitor.business.name", read_only=True)

    class Meta:
        model = MonitorResult
        fields = "__all__"
        read_only_fields = (
            "execution_key", "scheduled_at", "started_at", "checked_at", "finished_at"
        )
MonitorStateSerializer = serializer_for(MonitorState)
BusinessChainSerializer = serializer_for(BusinessChain)
ChainNodeSerializer = serializer_for(ChainNode)
ChainEdgeSerializer = serializer_for(ChainEdge)
IncidentTimelineSerializer = serializer_for(IncidentTimeline)


class IncidentSerializer(BaseSerializer):
    monitor_name = serializers.CharField(source="monitor.name", read_only=True)
    business_name = serializers.CharField(source="monitor.business.name", read_only=True)
    assignee_name = serializers.CharField(source="assignee.username", read_only=True)
    timeline = IncidentTimelineSerializer(many=True, read_only=True)

    class Meta:
        model = Incident
        fields = "__all__"


class AlertRuleSerializer(BaseSerializer):
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
        config = dict(attrs.get("config", getattr(self.instance, "config", {}) or {}))
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
        if channel_type == "EMAIL" and config.get("use_ssl") and config.get("use_tls"):
            raise serializers.ValidationError({"config": "SSL 与 STARTTLS 不能同时启用"})
        if config.get("timeout") is not None and not 1 <= float(config["timeout"]) <= 60:
            raise serializers.ValidationError({"config": "超时时间必须在 1 到 60 秒之间"})
        attrs["config"] = config
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
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
