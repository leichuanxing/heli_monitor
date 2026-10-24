import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.audit.models import AuditLog
from apps.businesses.models import BusinessGroup, BusinessSystem, Tag
from apps.monitors.models import Monitor


@pytest.fixture
def asset_api(db):
    client = APIClient()
    client.force_authenticate(User.objects.create_superuser("asset-admin"))
    return client


def test_group_cycles_duplicate_roots_and_delete_guard(asset_api):
    root = BusinessGroup.objects.create(name="Root")
    child = BusinessGroup.objects.create(name="Child", parent=root)
    assert (
        asset_api.patch(
            f"/api/v1/business-groups/{root.pk}/", {"parent": str(child.pk)}, format="json"
        ).status_code
        == 400
    )
    assert (
        asset_api.patch(
            f"/api/v1/business-groups/{root.pk}/", {"parent": str(root.pk)}, format="json"
        ).status_code
        == 400
    )
    assert (
        asset_api.post("/api/v1/business-groups/", {"name": "Root"}, format="json").status_code
        == 400
    )
    assert asset_api.delete(f"/api/v1/business-groups/{root.pk}/").status_code == 400
    assert not AuditLog.objects.filter(action="DELETE", resource_id=str(root.pk)).exists()
    assert asset_api.delete(f"/api/v1/business-groups/{child.pk}/").status_code == 204


@pytest.mark.parametrize("value", [-1, 100.001])
def test_business_sla_rejects_out_of_range(asset_api, value):
    response = asset_api.post(
        "/api/v1/business-systems/",
        {"name": "Business", "code": "invalid", "sla_target": value},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.parametrize("value", [0, 99.999, 100])
def test_business_sla_accepts_boundary_values(asset_api, value):
    response = asset_api.post(
        "/api/v1/business-systems/",
        {"name": "Business", "code": str(value), "sla_target": value},
        format="json",
    )
    assert response.status_code == 201


def test_business_archive_and_deletion_preserve_related_tasks(asset_api):
    business = BusinessSystem.objects.create(code="protected", name="Business")
    monitor = Monitor.objects.create(
        business=business, name="Keep task", monitor_type="TCP", target="example.com:443"
    )
    assert asset_api.delete(f"/api/v1/business-systems/{business.pk}/").status_code == 400
    assert Monitor.objects.filter(pk=monitor.pk).exists()
    assert not AuditLog.objects.filter(action="DELETE", resource_id=str(business.pk)).exists()
    response = asset_api.patch(
        f"/api/v1/business-systems/{business.pk}/", {"is_archived": True}, format="json"
    )
    assert response.status_code == 200 and response.data["is_enabled"] is False
    assert response.data["monitor_count"] == 1


def test_business_metadata_and_group_delete_guard(asset_api):
    group = BusinessGroup.objects.create(name="Used")
    business = BusinessSystem.objects.create(code="used", name="Used", group=group)
    assert asset_api.delete(f"/api/v1/business-groups/{group.pk}/").status_code == 400
    assert (
        asset_api.patch(
            f"/api/v1/business-systems/{business.pk}/", {"service_schedule": []}, format="json"
        ).status_code
        == 400
    )
    assert asset_api.get("/api/v1/business-systems/", {"group": str(group.pk)}).data["count"] == 1


@pytest.mark.parametrize("color", ["red", "javascript:bad", "#12", "#GGGGGG"])
def test_tag_color_validation(asset_api, color):
    assert (
        asset_api.post(
            "/api/v1/tags/", {"name": "Invalid", "color": color}, format="json"
        ).status_code
        == 400
    )


def test_tag_delete_only_removes_associations(asset_api):
    response = asset_api.post("/api/v1/tags/", {"name": "Blue", "color": "#aabbcc"}, format="json")
    assert response.status_code == 201 and response.data["color"] == "#AABBCC"
    business = BusinessSystem.objects.create(code="tagged", name="Tagged")
    business.tags.add(response.data["id"])
    assert asset_api.delete(f"/api/v1/tags/{response.data['id']}/").status_code == 204
    assert BusinessSystem.objects.filter(pk=business.pk).exists()
    assert business.tags.count() == 0


def test_asset_options_do_not_require_iam_permissions(asset_api):
    user = User.objects.create_user("asset-only", email="private@example.com")
    Role.objects.create(code="ASSET_ONLY", name="Asset only", permissions=["asset.view"]).users.add(
        user
    )
    asset_api.force_authenticate(user)
    assert asset_api.get("/api/v1/users/").status_code == 403
    response = asset_api.get("/api/v1/business-systems/options/")
    assert response.status_code == 200
    assert all(set(item) == {"id", "username"} for item in response.data["users"])
    assert asset_api.post("/api/v1/tags/", {"name": "Denied"}, format="json").status_code == 403
    assert not Tag.objects.filter(name="Denied").exists()


def test_root_group_creation_and_partial_duplicate_validation(asset_api):
    first = asset_api.post("/api/v1/business-groups/", {"name": "First root"}, format="json")
    assert first.status_code == 201
    second = asset_api.post("/api/v1/business-groups/", {"name": "Second root"}, format="json")
    assert second.status_code == 201
    assert (
        asset_api.patch(
            f"/api/v1/business-groups/{second.data['id']}/", {"name": "First root"}, format="json"
        ).status_code
        == 400
    )
