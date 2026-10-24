import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient


@pytest.fixture
def admin_client(db):
    client = APIClient()
    client.force_authenticate(
        User.objects.create_superuser("regression", password="StrongTestPass123!")
    )
    return client


@pytest.mark.django_db
@pytest.mark.parametrize(
    "resource",
    [
        "departments",
        "monitors",
        "business-chains",
        "chain-nodes",
        "chain-edges",
        "incidents",
        "alert-rules",
        "notification-channels",
        "notification-logs",
        "status-pages",
    ],
)
def test_inherited_ordering_never_causes_server_error(admin_client, resource):
    for field in ("name", "status", "created_at", "updated_at"):
        response = admin_client.get(f"/api/v1/{resource}/", {"ordering": field})
        assert response.status_code == 200, (resource, field, response.status_code)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {"dashboard_refresh_seconds": 5.9},
        {"dashboard_refresh_seconds": True},
        {"browser_title": None},
        {"browser_title": {"bad": "value"}},
    ],
)
def test_settings_reject_invalid_types(admin_client, payload):
    assert admin_client.patch("/api/v1/system/settings/", payload, format="json").status_code == 400


def test_public_branding_ignores_expired_auth(db):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer expired.invalid.token")
    assert client.get("/api/v1/public/branding/").status_code == 200
