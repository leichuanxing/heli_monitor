from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from apps.core.notifications import send_notification


@pytest.mark.parametrize(
    "kind,key",
    [("WECHAT", "webhook_url"), ("DINGTALK", "webhook_url"),
     ("WEBHOOK", "url"), ("SERVERCHAN", "sendkey")],
)
@pytest.mark.parametrize("accepted", [True, False])
def test_notification_transports_propagate_provider_result(kind, key, accepted):
    config = {key: "SCT-test" if kind == "SERVERCHAN" else "https://example.com/hook"}
    response = httpx.Response(
        200, json={"code": 0 if accepted else 400, "message": "provider rejected"},
        request=httpx.Request("POST", "https://example.com/hook"),
    )
    with patch("apps.core.notifications.validate_target"), patch(
        "apps.core.notifications.httpx.post", return_value=response
    ) as post:
        channel = SimpleNamespace(channel_type=kind, config=config)
        result = send_notification(channel, "故障", "测试")
    assert result["success"] is accepted
    post.assert_called_once()


@pytest.mark.parametrize("use_ssl,use_tls", [(True, False), (False, True)])
def test_smtp_transport_authenticates_and_sends(use_ssl, use_tls):
    config = {"host": "smtp.example.com", "from_email": "sender@example.com",
              "recipients": "one@example.com,two@example.com", "username": "sender",
              "password": "test-only", "use_ssl": use_ssl, "use_tls": use_tls}
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    name = "SMTP_SSL" if use_ssl else "SMTP"
    with patch("apps.core.notifications.validate_target"), patch(
        f"apps.core.notifications.smtplib.{name}", return_value=smtp
    ):
        channel = SimpleNamespace(channel_type="EMAIL", config=config)
        result = send_notification(channel, "恢复", "测试")
    assert result["success"] is True
    assert smtp.starttls.call_count == int(use_tls)
    smtp.login.assert_called_once_with("sender", "test-only")
    smtp.send_message.assert_called_once()


def test_notification_errors_do_not_expose_channel_secrets():
    channel = SimpleNamespace(channel_type="SERVERCHAN", config={"sendkey": "SCT-private-key"})
    with patch("apps.core.notifications.httpx.post", side_effect=RuntimeError(
        "Failed https://sctapi.ftqq.com/SCT-private-key.send"
    )):
        result = send_notification(channel, "故障", "测试")
    assert not result["success"]
    assert "SCT-private-key" not in result["message"]
    assert "https://" not in result["message"]
