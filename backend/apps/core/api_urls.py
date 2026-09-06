# ruff: noqa: F405
from django.urls import path
from rest_framework.routers import DefaultRouter

from .api import *  # noqa: F403

router = DefaultRouter()
for prefix, view in [
    ("departments", DepartmentViewSet),  # noqa: F405
    ("roles", RoleViewSet),  # noqa: F405
    ("users", UserViewSet),
    ("business-groups", BusinessGroupViewSet),
    ("tags", TagViewSet),
    ("business-systems", BusinessSystemViewSet),
    ("monitors", MonitorViewSet),
    ("monitor-results", MonitorResultViewSet),
    ("business-chains", BusinessChainViewSet),
    ("chain-nodes", ChainNodeViewSet),
    ("chain-edges", ChainEdgeViewSet),
    ("incidents", IncidentViewSet),
    ("alert-rules", AlertRuleViewSet),
    ("notification-channels", NotificationChannelViewSet),
    ("notification-logs", NotificationLogViewSet),
    ("maintenance-windows", MaintenanceWindowViewSet),
    ("status-pages", StatusPageViewSet),
    ("audit-logs", AuditLogViewSet),
    ("login-records", LoginRecordViewSet),
]:
    router.register(prefix, view, basename=prefix)
urlpatterns = router.urls + [
    path("auth/me/", current_user),
    path("dashboard/summary/", dashboard_summary),
    path("reports/sla/", sla_report),
    path("reports/sla/export.csv", sla_export),
    path("system/overview/", system_overview),
    path("system/settings/", system_settings),
    path("public/branding/", public_branding),
    path("system/maintenance/", system_maintenance),
    path("public/status/<slug:slug>/", public_status),
]
