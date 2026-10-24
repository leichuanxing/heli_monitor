from secrets import compare_digest

from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.utils import get_md5_hash_password
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.audit.models import LoginRecord


def _request_metadata(request):
    source_ip = request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR")
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:512]
    return source_ip, user_agent


class AuditedTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        request = self.context["request"]
        username = str(attrs.get(self.username_field, ""))[:150]
        source_ip, user_agent = _request_metadata(request)
        try:
            data = super().validate(attrs)
        except AuthenticationFailed:
            user = get_user_model().objects.filter(username=username).first()
            LoginRecord.objects.create(
                user=user,
                username=username,
                source_ip=source_ip,
                user_agent=user_agent,
                success=False,
                failure_reason="INVALID_CREDENTIALS",
            )
            raise
        LoginRecord.objects.create(
            user=self.user,
            username=self.user.get_username(),
            source_ip=source_ip,
            user_agent=user_agent,
            success=True,
        )
        return data


class AuditedTokenObtainPairView(TokenObtainPairView):
    serializer_class = AuditedTokenObtainPairSerializer


class RevokingTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        refresh = self.token_class(attrs["refresh"])
        user = (
            get_user_model()
            .objects.filter(pk=refresh.get(api_settings.USER_ID_CLAIM), is_active=True)
            .first()
        )
        if user is None or not compare_digest(
            str(refresh.get(api_settings.REVOKE_TOKEN_CLAIM, "")),
            get_md5_hash_password(user.password),
        ):
            raise AuthenticationFailed("登录凭据已失效，请重新登录")
        return super().validate(attrs)


class RevokingTokenRefreshView(TokenRefreshView):
    serializer_class = RevokingTokenRefreshSerializer
