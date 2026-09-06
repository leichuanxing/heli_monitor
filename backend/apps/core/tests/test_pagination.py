import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.businesses.models import Tag


@pytest.mark.django_db
def test_page_size_and_next_page_preserve_all_records():
    user = User.objects.create_superuser("pagination-admin", password="test-password")
    client = APIClient()
    client.force_authenticate(user)
    Tag.objects.bulk_create([Tag(name=f"page-tag-{i}") for i in range(55)])
    first = client.get("/api/v1/tags/", {"page_size": 30})
    second = client.get("/api/v1/tags/", {"page_size": 30, "page": 2})
    assert first.status_code == second.status_code == 200
    assert first.data["count"] == 55
    assert len(first.data["results"]) == 30
    assert len(second.data["results"]) == 25
    ids = {row["id"] for row in first.data["results"] + second.data["results"]}
    assert len(ids) == 55
    assert second.data["next"] is None
