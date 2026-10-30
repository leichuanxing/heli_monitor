"""Shared, side-effect-free validation for monitor configuration."""

import ipaddress
import re
from copy import deepcopy
from urllib.parse import urlparse

import sqlparse
from jsonpath_ng import parse as parse_jsonpath
from sqlparse import tokens

DATABASE_TYPES = {"MSSQL", "POSTGRESQL", "MYSQL", "MONGODB"}
SECRET_HEADERS = {"authorization", "proxy-authorization", "cookie", "x-api-key", "api-key"}


def host_port(target, default_port=None):
    target = str(target).strip()
    if (
        not target
        or any(x in target for x in ("/", "?", "#", "@"))
        or any(c.isspace() for c in target)
    ):
        raise ValueError("请输入主机名、IP 或 主机:端口，不要包含协议或路径")
    if target.startswith("["):
        match = re.fullmatch(r"\[([^]]+)\](?::(\d+))?", target)
        if not match:
            raise ValueError("IPv6 格式应为 [地址]:端口")
        host, raw_port = match.groups()
        ipaddress.IPv6Address(host)
        port = int(raw_port) if raw_port else default_port
    elif target.count(":") > 1:
        ipaddress.IPv6Address(target)
        host, port = target, default_port
    elif ":" in target:
        host, raw_port = target.rsplit(":", 1)
        if not raw_port.isdigit():
            raise ValueError("端口必须为 1 到 65535 的整数")
        port = int(raw_port)
    else:
        host, port = target, default_port
    if not host or (port is not None and not 1 <= port <= 65535):
        raise ValueError("主机或端口无效")
    if port is None and default_port is None:
        raise ValueError("请输入 主机:端口")
    return host, port


def read_query(query):
    query = str(query or "SELECT 1").strip()
    statements = sqlparse.parse(query)
    message = "仅允许 SELECT 或 WITH 只读查询，禁止多语句和写入操作"
    if len(statements) != 1 or statements[0].get_type() != "SELECT":
        raise ValueError(message)
    for token in statements[0].flatten():
        if token.ttype in tokens.DDL or (
            token.ttype in tokens.DML and token.normalized != "SELECT"
        ):
            raise ValueError(message)
        if token.ttype in tokens.Keyword and token.normalized in {"INTO", "FOR", "LOCK", "OUTFILE"}:
            raise ValueError(message)
    return query


def number(config, key, low, high, integer=True):
    if key not in config or config[key] is None:
        return
    value = config[key]
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or (integer and int(value) != value)
    ):
        raise ValueError(f"{key} 必须为{'整数' if integer else '数值'}")
    if not low <= value <= high:
        raise ValueError(f"{key} 必须在 {low} 到 {high} 之间")


def validate_config(kind, target, config):
    config = deepcopy(config)
    config.pop("timeout", None)
    for key in ("follow_redirects", "verify_tls", "use_tls", "auth_enabled", "send_escapes"):
        if key in config and not isinstance(config[key], bool):
            raise ValueError(f"{key} 必须为布尔值")
    if kind in {"HTTP", "API"}:
        validate_http(target, config)
    elif kind == "TCP":
        host_port(target)
        number(config, "receive_bytes", 256, 65536)
        if any(key in config and not isinstance(config[key], str) for key in ("send", "expect")):
            raise ValueError("TCP 发送内容和期望返回必须为文本")
    elif kind in {"PING", "DNS"}:
        if (
            not target
            or any(c.isspace() for c in target)
            or any(c in target for c in ("/", "?", "#", "@"))
            or target.startswith("-")
        ):
            raise ValueError("请输入域名或 IP，不要包含协议、路径或命令参数")
        if kind == "PING":
            number(config, "count", 1, 10)
            number(config, "max_packet_loss", 0, 99, integer=False)
        else:
            if config.get("record_type", "A") not in {
                "A",
                "AAAA",
                "CNAME",
                "MX",
                "TXT",
                "NS",
                "SRV",
            }:
                raise ValueError("不支持的 DNS 记录类型")
            if config.get("server"):
                ipaddress.ip_address(config["server"])
            if not isinstance(config.get("expected", []), list) or any(
                not isinstance(x, str) for x in config.get("expected", [])
            ):
                raise ValueError("DNS 期望记录必须为字符串列表")
    elif kind == "SSL":
        host_port(target, 443)
        number(config, "warn_days", 1, 3650)
        if config.get("expiry_action", "warn") not in {"warn", "fail", "notify"}:
            raise ValueError("证书预警方式必须为 warn、notify 或 fail")
    elif kind in DATABASE_TYPES:
        validate_database(kind, target, config)
    return config


def validate_http(target, config):
    parsed = urlparse(target)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("请输入完整 HTTP/HTTPS URL；认证信息请填写在认证选项中")
    _ = parsed.port
    method = str(config.get("method", "GET")).upper()
    if method not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}:
        raise ValueError("不支持的 HTTP 请求方法")
    config["method"] = method
    for key in ("headers", "params", "form"):
        if config.get(key) is not None and not isinstance(config[key], dict):
            raise ValueError(f"{key} 必须是 JSON 对象")
    if any(not isinstance(v, str) for v in (config.get("headers") or {}).values()):
        raise ValueError("请求头的值必须为字符串")
    if config.get("body") is not None and not isinstance(config["body"], str):
        raise ValueError("文本请求体必须为字符串")
    if sum(config.get(key) is not None for key in ("json", "form", "body")) > 1:
        raise ValueError("json、form、body 三种请求体只能配置一种")
    statuses = config.get("expected_status")
    if statuses is not None:
        statuses = [statuses] if type(statuses) is int else statuses
        if (
            not isinstance(statuses, list)
            or not statuses
            or any(type(v) is not int or not 100 <= v <= 599 for v in statuses)
        ):
            raise ValueError("期望状态码必须为 100 到 599 的整数列表；留空默认全部 2xx")
        config["expected_status"] = sorted(set(statuses))
    if "keywords" in config and (
        not isinstance(config["keywords"], list)
        or any(not isinstance(x, str) for x in config["keywords"])
    ):
        raise ValueError("关键字必须为字符串列表")
    if config.get("regex"):
        try:
            re.compile(config["regex"])
        except (re.error, TypeError) as exc:
            raise ValueError("正则表达式无效") from exc
    rules = config.get("json_assertions", [])
    if not isinstance(rules, list) or len(rules) > 20:
        raise ValueError("JSON 断言必须为列表，最多 20 条")
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("path"), str):
            raise ValueError("每条 JSON 断言必须包含 path")
        try:
            parse_jsonpath(rule["path"])
        except Exception as exc:
            raise ValueError("JSONPath 表达式无效") from exc
    number(config, "max_body_bytes", 1024, 1048576)
    auth = config.get("auth") or {}
    required = {
        "none": (),
        "": (),
        "bearer": ("token",),
        "basic": ("username", "password"),
        "api_key": ("name", "value"),
        "oauth2_client_credentials": ("token_url", "client_id", "client_secret"),
    }
    auth_type = str(auth.get("type", "none")).lower()
    if auth_type not in required or any(not auth.get(k) for k in required.get(auth_type, ())):
        raise ValueError("认证方式无效或缺少必填认证参数")
    if auth_type == "api_key" and auth.get("in", "header") not in {"header", "query"}:
        raise ValueError("API Key 传递位置必须为 header 或 query")
    if auth_type == "oauth2_client_credentials":
        url = urlparse(str(auth["token_url"]))
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.fragment
        ):
            raise ValueError("Token URL 必须为完整 HTTP/HTTPS 地址")
        for key in ("token_params", "token_headers"):
            if key in auth and not isinstance(auth[key], dict):
                raise ValueError(f"{key} 必须是 JSON 对象")


def validate_database(kind, target, config):
    host_port(target, {"MSSQL": 1433, "POSTGRESQL": 5432, "MYSQL": 3306, "MONGODB": 27017}[kind])
    required = (
        ("database",)
        if kind == "MONGODB" and config.get("auth_enabled") is False
        else ("database", "username", "password")
    )
    if any(not config.get(k) for k in required):
        raise ValueError("数据库配置缺少必填参数：" + ", ".join(required))
    if kind != "MONGODB":
        config["query"] = read_query(config.get("query", "SELECT 1"))
    if config.get("expected_value") == "":
        config.pop("expected_value")
    if kind == "POSTGRESQL" and config.get("sslmode", "prefer") not in {
        "disable",
        "allow",
        "prefer",
        "require",
        "verify-ca",
        "verify-full",
    }:
        raise ValueError("PostgreSQL SSL 模式无效")
    if kind == "MSSQL" and config.get("tds_version", "7.4") not in {"7.1", "7.2", "7.3", "7.4"}:
        raise ValueError("TDS 版本无效")
