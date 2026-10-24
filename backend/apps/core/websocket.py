from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser, User
from django.urls import path
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .permissions import user_permissions


@database_sync_to_async
def user_from_token(raw_token):
    try:
        authentication = JWTAuthentication()
        validated = authentication.get_validated_token(raw_token)
        return authentication.get_user(validated)
    except (AuthenticationFailed, InvalidToken, TokenError, User.DoesNotExist):
        return AnonymousUser()


class JwtAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token = query.get("token", [""])[0]
        scope["user"] = await user_from_token(token) if token else AnonymousUser()
        return await self.app(scope, receive, send)


@database_sync_to_async
def can_view_monitors(user):
    return "monitor.view" in user_permissions(user)


class StatusConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        if not self.scope["user"].is_authenticated:
            await self.close(code=4401)
            return
        if not await can_view_monitors(self.scope["user"]):
            await self.close(code=4403)
            return
        await self.channel_layer.group_add("monitor-status", self.channel_name)
        await self.accept()
        await self.send_json({"type": "connected", "message": "monitor status stream ready"})

    async def disconnect(self, code):
        await self.channel_layer.group_discard("monitor-status", self.channel_name)

    async def status_update(self, event):
        await self.send_json(event["payload"])


websocket_urlpatterns = [path("ws/v1/status/", StatusConsumer.as_asgi())]
