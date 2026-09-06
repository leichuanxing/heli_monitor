from unittest.mock import patch

import httpx

from apps.core.probes import http_probe


def response(status=204, json_data=None):
    request = httpx.Request("GET", "https://api.example.com/health")
    if json_data is not None:
        return httpx.Response(status, json=json_data, request=request)
    return httpx.Response(status, text="", request=request)


@patch("apps.core.probes.validate_target")
@patch("apps.core.probes.httpx.request")
def test_api_probe_accepts_all_2xx_and_bearer_auth(request_mock, _validate):
    request_mock.return_value = response(204)
    result = http_probe(
        "https://api.example.com/health",
        {"auth": {"type": "bearer", "token": "secret-token"}},
    )
    assert result["success"] is True
    assert request_mock.call_args.kwargs["headers"]["Authorization"] == "Bearer secret-token"


@patch("apps.core.probes.validate_target")
@patch("apps.core.probes.httpx.request")
def test_api_probe_supports_basic_and_query_api_key(request_mock, _validate):
    request_mock.return_value = response(200)
    basic = http_probe(
        "https://api.example.com/health",
        {"auth": {"type": "basic", "username": "probe", "password": "secret"}},
    )
    assert basic["success"] is True
    assert isinstance(request_mock.call_args.kwargs["auth"], httpx.BasicAuth)

    request_mock.return_value = response(200)
    api_key = http_probe(
        "https://api.example.com/health",
        {"auth": {"type": "api_key", "in": "query", "name": "key", "value": "abc"}},
    )
    assert api_key["success"] is True
    assert request_mock.call_args.kwargs["params"] == {"key": "abc"}


@patch("apps.core.probes.validate_target")
@patch("apps.core.probes.httpx.request")
@patch("apps.core.probes.httpx.post")
def test_api_probe_supports_oauth2_client_credentials(post_mock, request_mock, _validate):
    post_mock.return_value = response(
        200, {"access_token": "oauth-token", "token_type": "Bearer"}
    )
    request_mock.return_value = response(200)
    result = http_probe(
        "https://api.example.com/health",
        {
            "auth": {
                "type": "oauth2_client_credentials",
                "token_url": "https://auth.example.com/token",
                "client_id": "monitor",
                "client_secret": "secret",
            }
        },
    )
    assert result["success"] is True
    assert request_mock.call_args.kwargs["headers"]["Authorization"] == "Bearer oauth-token"


@patch("apps.core.probes.validate_target")
@patch("apps.core.probes.httpx.request")
def test_api_probe_reports_authentication_failure(request_mock, _validate):
    request_mock.return_value = response(401)
    result = http_probe("https://api.example.com/health", {})
    assert result["success"] is False
    assert result["error_type"] == "AUTH_ERROR"
    assert result["error_summary"] == "接口认证失败"
