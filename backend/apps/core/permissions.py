from rest_framework.permissions import BasePermission

PERMISSION_CATALOG = [
    {
        "group": "监控中心",
        "items": [("monitor.view", "查看监控"), ("monitor.manage", "管理探测任务")],
    },
    {
        "group": "资产管理",
        "items": [("asset.view", "查看业务资产"), ("asset.manage", "管理业务资产")],
    },
    {
        "group": "事件与告警",
        "items": [("alert.view", "查看事件告警"), ("alert.manage", "处理事件与配置告警")],
    },
    {
        "group": "维护与报表",
        "items": [("report.view", "查看维护与报表"), ("report.manage", "管理维护窗口与状态页")],
    },
    {
        "group": "组织与权限",
        "items": [("iam.view", "查看组织用户"), ("iam.manage", "管理组织、角色和用户")],
    },
    {
        "group": "系统管理",
        "items": [
            ("system.view", "查看系统健康与审计"),
            ("system.manage", "执行系统维护操作"),
        ],
    },
]
VALID_PERMISSIONS = {code for group in PERMISSION_CATALOG for code, _ in group["items"]}

RESOURCE_GROUPS = {
    "departments": "iam", "roles": "iam", "users": "iam",
    "business-groups": "asset", "tags": "asset", "business-systems": "asset",
    "monitors": "monitor", "monitor-results": "monitor", "business-chains": "monitor",
    "chain-nodes": "monitor", "chain-edges": "monitor",
    "incidents": "alert", "alert-rules": "alert", "notification-channels": "alert",
    "notification-logs": "alert", "maintenance-windows": "report", "status-pages": "report",
    "audit-logs": "system",
}


def user_permissions(user):
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return VALID_PERMISSIONS
    roles = user.business_roles.filter(is_enabled=True)
    result = {item for role in roles for item in (role.permissions or [])}
    legacy = set(roles.values_list("code", flat=True))
    if legacy & {"SUPER_ADMIN", "ADMIN"}:
        return VALID_PERMISSIONS
    if "OPERATOR" in legacy and not result:
        return VALID_PERMISSIONS - {"iam.manage"}
    return result


class HasResourcePermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        group = RESOURCE_GROUPS.get(getattr(view, "basename", ""))
        if not group:
            return True
        suffix = "view" if request.method in ("GET", "HEAD", "OPTIONS") else "manage"
        return f"{group}.{suffix}" in user_permissions(request.user)


IsOperatorOrReadOnly = HasResourcePermission


class HasSystemViewPermission(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and "system.view" in user_permissions(request.user)


class HasSystemManagePermission(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and "system.manage" in user_permissions(request.user)
