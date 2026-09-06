from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

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
