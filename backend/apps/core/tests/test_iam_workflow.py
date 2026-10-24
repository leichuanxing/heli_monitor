import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Department, Role, UserProfile


@pytest.fixture
def api(db):
    client = APIClient()
    client.force_authenticate(User.objects.create_superuser("iam-admin"))
    return client


@pytest.fixture
def manager(api):
    user = User.objects.create_user("limited-manager")
    role = Role.objects.create(
        name="IAM manager", code="IAM-MANAGER", permissions=["iam.view", "iam.manage"]
    )
    user.business_roles.add(role)
    api.force_authenticate(user)
    return user


@pytest.mark.parametrize("permissions", [[{}], [1], {"iam.manage": True}])
def test_role_invalid_permissions_return_400(api, permissions):
    response = api.post(
        "/api/v1/roles/",
        {"name": "Malformed", "code": "MALFORMED", "permissions": permissions},
        format="json",
    )
    assert response.status_code == 400


def test_manager_cannot_escalate_roles_or_assign_system_roles(api, manager):
    for code, permissions in [("ESCALATE", ["system.manage"]), ("ADMIN", [])]:
        response = api.post(
            "/api/v1/roles/",
            {"name": code, "code": code, "permissions": permissions},
            format="json",
        )
        assert response.status_code == 400
    role = Role.objects.create(name="Powerful", code="POWERFUL", permissions=["system.manage"])
    user = User.objects.create_user("ordinary")
    assert (
        api.patch(f"/api/v1/users/{user.pk}/", {"roles": [str(role.pk)]}, format="json").status_code
        == 400
    )
    assert (
        api.patch(f"/api/v1/roles/{role.pk}/", {"permissions": []}, format="json").status_code
        == 400
    )


def test_superuser_self_and_last_admin_protection(api, manager):
    admin = User.objects.get(username="iam-admin")
    assert (
        api.patch(f"/api/v1/users/{admin.pk}/", {"is_active": False}, format="json").status_code
        == 400
    )
    assert api.delete(f"/api/v1/users/{admin.pk}/").status_code == 400
    assert (
        api.patch(f"/api/v1/users/{manager.pk}/", {"is_active": False}, format="json").status_code
        == 400
    )
    assert (
        api.patch(f"/api/v1/users/{manager.pk}/", {"roles": []}, format="json").status_code == 400
    )
    role = manager.business_roles.first()
    assert (
        api.patch(f"/api/v1/roles/{role.pk}/", {"is_enabled": False}, format="json").status_code
        == 400
    )
    api.force_authenticate(admin)
    assert (
        api.patch(f"/api/v1/users/{admin.pk}/", {"is_active": False}, format="json").status_code
        == 400
    )


def test_department_cycle_duplicate_and_association_guards(api):
    root = Department.objects.create(name="Root", code="ROOT")
    child = Department.objects.create(name="Child", code="CHILD", parent=root)
    assert (
        api.patch(
            f"/api/v1/departments/{root.pk}/", {"parent": str(child.pk)}, format="json"
        ).status_code
        == 400
    )
    assert (
        api.post(
            "/api/v1/departments/", {"name": "Root", "code": "OTHER"}, format="json"
        ).status_code
        == 400
    )
    assert api.delete(f"/api/v1/departments/{root.pk}/").status_code == 400
    user = User.objects.create_user("member")
    UserProfile.objects.create(user=user, department=child)
    assert api.delete(f"/api/v1/departments/{child.pk}/").status_code == 400


def test_assigned_role_delete_and_disabled_associations(api):
    role = Role.objects.create(name="Disabled", code="DISABLED", is_enabled=False)
    user = User.objects.create_user("member")
    user.business_roles.add(role)
    assert api.delete(f"/api/v1/roles/{role.pk}/").status_code == 400
    assert (
        api.patch(f"/api/v1/users/{user.pk}/", {"roles": [str(role.pk)]}, format="json").status_code
        == 200
    )
    other = User.objects.create_user("other")
    assert (
        api.patch(
            f"/api/v1/users/{other.pk}/", {"roles": [str(role.pk)]}, format="json"
        ).status_code
        == 400
    )
    department = Department.objects.create(name="Disabled dept", code="DISABLED", is_enabled=False)
    UserProfile.objects.update_or_create(user=user, defaults={"department": department})
    assert (
        api.patch(
            f"/api/v1/users/{user.pk}/", {"department": str(department.pk)}, format="json"
        ).status_code
        == 200
    )
    assert (
        api.patch(
            f"/api/v1/users/{other.pk}/", {"department": str(department.pk)}, format="json"
        ).status_code
        == 400
    )


def test_password_policy_and_old_token_revocation(api):
    assert api.post("/api/v1/users/", {"username": "missing"}, format="json").status_code == 400
    assert (
        api.post(
            "/api/v1/users/", {"username": "weak", "password": "123456789012"}, format="json"
        ).status_code
        == 400
    )
    user = User.objects.create_user("session-user", password="Original!Secret2026")
    token = RefreshToken.for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    assert client.get("/api/v1/auth/me/").status_code == 200
    response = api.patch(
        f"/api/v1/users/{user.pk}/", {"password": "Replacement!Secret2026"}, format="json"
    )
    assert response.status_code == 200
    assert "password" not in response.data
    assert client.get("/api/v1/auth/me/").status_code == 401
    assert (
        client.post("/api/v1/auth/refresh/", {"refresh": str(token)}, format="json").status_code
        == 401
    )


def test_role_permissions_change_applies_to_existing_token(api):
    user = User.objects.create_user("role-session")
    role = Role.objects.create(
        name="Read monitors", code="READ-MONITORS", permissions=["monitor.view"]
    )
    user.business_roles.add(role)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    assert client.get("/api/v1/monitors/").status_code == 200
    assert (
        api.patch(f"/api/v1/roles/{role.pk}/", {"is_enabled": False}, format="json").status_code
        == 200
    )
    assert client.get("/api/v1/monitors/").status_code == 403
    assert (
        api.patch(f"/api/v1/users/{user.pk}/", {"is_active": False}, format="json").status_code
        == 200
    )
    assert client.get("/api/v1/auth/me/").status_code == 401
