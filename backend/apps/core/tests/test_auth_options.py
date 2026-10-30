import pytest

from apps.core.monitor_config import validate_config


def test_removed_login_token_is_rejected():
    with pytest.raises(ValueError, match="认证方式无效"):
        validate_config(
            "API",
            "https://example.com/api",
            {
                "auth": {
                    "type": "login_token",
                    "token_url": "https://example.com/login",
                    "username": "test",
                    "password": "synthetic",
                }
            },
        )


@pytest.mark.parametrize(
    "auth",
    [
        {"type": "none"},
        {"type": "bearer", "token": "synthetic"},
        {"type": "basic", "username": "test", "password": "synthetic"},
        {"type": "api_key", "name": "X-Key", "value": "synthetic"},
        {
            "type": "oauth2_client_credentials",
            "token_url": "https://example.com/oauth",
            "client_id": "test",
            "client_secret": "synthetic",
        },
    ],
)
def test_other_authentication_modes_remain_available(auth):
    assert validate_config("API", "https://example.com/api", {"auth": auth})["auth"] == auth
