from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenBlacklistView, TokenRefreshView

from apps.core.auth import AuditedTokenObtainPairView

urlpatterns = [
    path("health/", include("apps.core.urls")),
    path("api/v1/auth/login/", AuditedTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/v1/auth/logout/", TokenBlacklistView.as_view(), name="token_blacklist"),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/v1/", include("apps.core.api_urls")),
]
