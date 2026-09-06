import ipaddress
import os
import re
import socket
import ssl
import subprocess
import time
from datetime import UTC, datetime
from urllib.parse import urlparse

import dns.resolver
import httpx
import psycopg
import pymssql
import pymysql
from jsonpath_ng import parse as jsonpath_parse
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure, ServerSelectionTimeoutError

from .secrets import decrypt_secret

ERRORS = (
    "DNS_ERROR",
    "CONNECT_TIMEOUT",
    "CONNECT_REFUSED",
    "READ_TIMEOUT",
    "TLS_ERROR",
    "HTTP_ERROR",
    "AUTH_ERROR",
    "ASSERTION_FAILED",
    "INVALID_TARGET",
    "PROBE_ERROR",
    "UNKNOWN_ERROR",
)


def _result(success, started, **kwargs):
    return {
        "success": success,
        "checked_at": datetime.now(UTC).isoformat(),
        "latency_ms": round((time.monotonic() - started) * 1000, 2),
        "metrics": kwargs.pop("metrics", {}),
        "assertions": kwargs.pop("assertions", []),
        "error_type": kwargs.pop("error_type", None),
        "error_summary": kwargs.pop("error_summary", None),
        "detail": kwargs.pop("detail", {}),
        **kwargs,
    }


def _allowed_ip(value):
    ip = ipaddress.ip_address(value)
    allowed = [
        ipaddress.ip_network(x.strip())
        for x in os.getenv("ALLOWED_PROBE_CIDRS", "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16").split(
            ","
        )
        if x.strip()
    ]
    if (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip in ipaddress.ip_network("169.254.169.254/32")
    ):
        return False
    if ip.is_private:
        return any(ip in network for network in allowed)
    return True


def validate_target(host, port=None):
    if port and int(port) in {
        int(x) for x in os.getenv("BLOCKED_PROBE_PORTS", "25,445").split(",") if x
    }:
        raise ValueError("目标端口被安全策略禁止")
    infos = socket.getaddrinfo(host, port or 0, type=socket.SOCK_STREAM)
    if not infos or any(not _allowed_ip(x[4][0]) for x in infos):
        raise ValueError("目标地址不在允许探测范围")
    return infos


def _validated_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("URL 协议或主机无效")
    validate_target(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    return parsed


def _prepare_auth(config, headers, params):
    auth_config = config.get("auth") or {}
    auth_type = str(auth_config.get("type", "none")).lower()
    request_auth = None
    if auth_type in ("", "none"):
        return request_auth
    if auth_type == "bearer":
        headers["Authorization"] = f"Bearer {auth_config.get('token', '')}"
    elif auth_type == "basic":
        request_auth = httpx.BasicAuth(
            str(auth_config.get("username", "")), str(auth_config.get("password", ""))
        )
    elif auth_type == "api_key":
        name = str(auth_config.get("name", "X-API-Key"))
        value = str(auth_config.get("value", ""))
        if auth_config.get("in", "header") == "query":
            params[name] = value
        else:
            headers[name] = value
    elif auth_type == "oauth2_client_credentials":
        token_url = str(auth_config.get("token_url", ""))
        _validated_url(token_url)
        token_response = httpx.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": auth_config.get("client_id", ""),
                "client_secret": auth_config.get("client_secret", ""),
                **(auth_config.get("token_params") or {}),
            },
            headers=auth_config.get("token_headers") or {},
            timeout=float(config.get("timeout", 10)),
        )
        token_response.raise_for_status()
        token_payload = token_response.json()
        token = token_payload.get("access_token")
        if not token:
            raise PermissionError("OAuth2 响应缺少 access_token")
        headers["Authorization"] = f"{token_payload.get('token_type', 'Bearer')} {token}"
    else:
        raise ValueError(f"不支持的认证类型：{auth_type}")
    return request_auth


def http_probe(target, config):
    started = time.monotonic()
    assertions = []
    try:
        _validated_url(target)
        headers = dict(config.get("headers", {}))
        params = dict(config.get("params") or {})
        request_auth = _prepare_auth(config, headers, params)
        sensitive = {"authorization", "cookie"}
        response = httpx.request(
            str(config.get("method", "GET")).upper(),
            target,
            headers=headers,
            params=params,
            json=config.get("json"),
            data=config.get("form"),
            content=config.get("body"),
            auth=request_auth,
            timeout=float(config.get("timeout", 10)),
            follow_redirects=bool(config.get("follow_redirects", True)),
            verify=bool(config.get("verify_tls", True)),
        )
        expected = config.get("expected_status")
        expected = list(range(200, 300)) if expected is None else expected
        expected = [expected] if isinstance(expected, int) else list(expected)
        assertions.append(
            {
                "type": "status_code",
                "success": response.status_code in expected,
                "actual": response.status_code,
                "expected": expected,
            }
        )
        body = response.text[: int(config.get("max_body_bytes", 65536))]
        for keyword in config.get("keywords", []):
            assertions.append({"type": "keyword", "success": keyword in body, "expected": keyword})
        if config.get("regex"):
            assertions.append(
                {
                    "type": "regex",
                    "success": bool(re.search(config["regex"], body)),
                    "expected": config["regex"],
                }
            )
        if config.get("json_assertions"):
            payload = response.json()
            for rule in config["json_assertions"]:
                values = [m.value for m in jsonpath_parse(rule["path"]).find(payload)]
                ok = bool(values) and ("value" not in rule or rule["value"] in values)
                assertions.append(
                    {"type": "jsonpath", "path": rule["path"], "success": ok, "actual": values[:5]}
                )
        success = all(a["success"] for a in assertions)
        auth_failed = response.status_code in (401, 403)
        return _result(
            success,
            started,
            status_code=response.status_code,
            assertions=assertions,
            error_type=None if success else ("AUTH_ERROR" if auth_failed else "ASSERTION_FAILED"),
            error_summary=None if success else ("接口认证失败" if auth_failed else "响应断言失败"),
            detail={
                "final_url": str(response.url),
                "headers": {
                    k: v for k, v in response.headers.items() if k.lower() not in sensitive
                },
            },
        )
    except ValueError as e:
        return _result(False, started, error_type="INVALID_TARGET", error_summary=str(e))
    except PermissionError as e:
        return _result(False, started, error_type="AUTH_ERROR", error_summary=str(e))
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        return _result(
            False,
            started,
            status_code=status,
            error_type="AUTH_ERROR" if status in (400, 401, 403) else "HTTP_ERROR",
            error_summary=f"认证令牌请求失败（HTTP {status}）",
        )
    except httpx.ConnectTimeout:
        return _result(False, started, error_type="CONNECT_TIMEOUT", error_summary="连接超时")
    except httpx.ReadTimeout:
        return _result(False, started, error_type="READ_TIMEOUT", error_summary="读取超时")
    except httpx.ConnectError as e:
        return _result(False, started, error_type="CONNECT_REFUSED", error_summary=str(e)[:300])
    except ssl.SSLError as e:
        return _result(False, started, error_type="TLS_ERROR", error_summary=str(e)[:300])
    except Exception as e:
        return _result(False, started, error_type="PROBE_ERROR", error_summary=str(e)[:300])


def tcp_probe(target, config):
    started = time.monotonic()
    try:
        host, port = target.rsplit(":", 1)
        port = int(port)
        validate_target(host, port)
        with socket.create_connection(
            (host, port), timeout=float(config.get("timeout", 10))
        ) as sock:
            if config.get("send"):
                sock.sendall(config["send"].encode())
            received = sock.recv(4096).decode(errors="replace") if config.get("expect") else ""
        ok = not config.get("expect") or config["expect"] in received
        return _result(
            ok,
            started,
            assertions=[{"type": "contains", "success": ok}] if config.get("expect") else [],
            error_type=None if ok else "ASSERTION_FAILED",
            error_summary=None if ok else "TCP 返回内容不匹配",
        )
    except ValueError as e:
        return _result(False, started, error_type="INVALID_TARGET", error_summary=str(e))
    except TimeoutError:
        return _result(False, started, error_type="CONNECT_TIMEOUT", error_summary="连接超时")
    except ConnectionRefusedError:
        return _result(False, started, error_type="CONNECT_REFUSED", error_summary="连接被拒绝")
    except Exception as e:
        return _result(False, started, error_type="PROBE_ERROR", error_summary=str(e)[:300])


def dns_probe(target, config):
    started = time.monotonic()
    try:
        resolver = dns.resolver.Resolver(configure=True)
        if config.get("server"):
            resolver.nameservers = [config["server"]]
        resolver.timeout = resolver.lifetime = float(config.get("timeout", 10))
        answer = resolver.resolve(target, config.get("record_type", "A"))
        values = sorted(str(x).rstrip(".") for x in answer)
        expected = sorted(str(x).rstrip(".") for x in config.get("expected", []))
        ok = not expected or all(x in values for x in expected)
        return _result(
            ok,
            started,
            metrics={"ttl": answer.rrset.ttl},
            detail={"records": values, "rcode": "NOERROR"},
            assertions=[
                {"type": "dns_records", "success": ok, "expected": expected, "actual": values}
            ],
            error_type=None if ok else "ASSERTION_FAILED",
            error_summary=None if ok else "DNS 记录不符合预期",
        )
    except dns.resolver.NXDOMAIN:
        return _result(
            False,
            started,
            error_type="DNS_ERROR",
            error_summary="NXDOMAIN",
            detail={"rcode": "NXDOMAIN"},
        )
    except dns.exception.Timeout:
        return _result(False, started, error_type="DNS_ERROR", error_summary="DNS 查询超时")
    except Exception as e:
        return _result(False, started, error_type="DNS_ERROR", error_summary=str(e)[:300])


def ssl_probe(target, config):
    started = time.monotonic()
    try:
        host, port = target.rsplit(":", 1) if ":" in target else (target, "443")
        port = int(port)
        validate_target(host, port)
        context = ssl.create_default_context()
        with socket.create_connection(
            (host, port), timeout=float(config.get("timeout", 10))
        ) as raw:
            with context.wrap_socket(raw, server_hostname=host) as conn:
                conn.getpeercert(binary_form=True)
                info = conn.getpeercert()
        expires = datetime.strptime(info["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
        days = (expires - datetime.now(UTC)).days
        warn = int(config.get("warn_days", 30))
        ok = days > 0
        return _result(
            ok,
            started,
            ssl_days_remaining=days,
            metrics={"days_remaining": days, "warning": days <= warn},
            detail={
                "subject": info.get("subject"),
                "issuer": info.get("issuer"),
                "not_after": expires.isoformat(),
            },
            error_type=None if ok else "TLS_ERROR",
            error_summary=None if ok else "证书已过期",
        )
    except ValueError as e:
        return _result(False, started, error_type="INVALID_TARGET", error_summary=str(e))
    except ssl.SSLError as e:
        return _result(False, started, error_type="TLS_ERROR", error_summary=str(e)[:300])
    except Exception as e:
        return _result(False, started, error_type="PROBE_ERROR", error_summary=str(e)[:300])


def ping_probe(target, config):
    started = time.monotonic()
    try:
        validate_target(target)
        count = min(max(int(config.get("count", 3)), 1), 10)
        timeout = max(int(config.get("timeout", 5)), 1)
        proc = subprocess.run(
            ["ping", "-c", str(count), "-W", str(timeout), target],
            capture_output=True,
            text=True,
            timeout=timeout * count + 2,
            check=False,
        )
        match = re.search(r"(\d+(?:\.\d+)?)% packet loss", proc.stdout)
        loss = float(match.group(1)) if match else 100.0
        latency = re.search(r"= [\d.]+/([\d.]+)/", proc.stdout)
        avg = float(latency.group(1)) if latency else None
        ok = proc.returncode == 0
        result = _result(
            ok,
            started,
            metrics={"packet_loss": loss, "average_ms": avg},
            error_type=None if ok else "CONNECT_TIMEOUT",
            error_summary=None if ok else "Ping 不可达",
        )
        result["packet_loss"] = loss
        result["latency_ms"] = avg
        return result
    except ValueError as e:
        return _result(False, started, error_type="INVALID_TARGET", error_summary=str(e))
    except Exception as e:
        return _result(False, started, error_type="PROBE_ERROR", error_summary=str(e)[:300])


DATABASE_PORTS = {"MSSQL": 1433, "POSTGRESQL": 5432, "MYSQL": 3306, "MONGODB": 27017}


def _database_target(target, kind):
    host, separator, raw_port = str(target).strip().rpartition(":")
    if separator and host and raw_port.isdigit():
        port = int(raw_port)
    else:
        host, port = str(target).strip(), DATABASE_PORTS[kind]
    if not host or not 1 <= port <= 65535:
        raise ValueError("数据库目标格式无效，请输入 主机:端口")
    validate_target(host, port)
    return host, port


def database_probe(kind, target, config):
    started = time.monotonic()
    connection = None
    try:
        host, port = _database_target(target, kind)
        timeout = max(1, int(config.get("timeout", 10)))
        username = str(config.get("username", ""))
        password = decrypt_secret(config.get("password", ""))
        database = str(config.get("database", ""))
        if not username or not database:
            raise ValueError("数据库名称和登录用户名不能为空")

        if kind == "POSTGRESQL":
            connection = psycopg.connect(
                host=host,
                port=port,
                dbname=database,
                user=username,
                password=password,
                connect_timeout=timeout,
                sslmode=str(config.get("sslmode", "prefer")),
            )
            query_started = time.monotonic()
            with connection.cursor() as cursor:
                cursor.execute(str(config.get("query", "SELECT 1")))
                value = cursor.fetchone()
        elif kind == "MYSQL":
            connection = pymysql.connect(
                host=host,
                port=port,
                database=database,
                user=username,
                password=password,
                connect_timeout=timeout,
                read_timeout=timeout,
                write_timeout=timeout,
                charset="utf8mb4",
                ssl={} if config.get("use_tls") else None,
            )
            query_started = time.monotonic()
            with connection.cursor() as cursor:
                cursor.execute(str(config.get("query", "SELECT 1")))
                value = cursor.fetchone()
        elif kind == "MSSQL":
            connection = pymssql.connect(
                server=host,
                port=str(port),
                database=database,
                user=username,
                password=password,
                login_timeout=timeout,
                timeout=timeout,
                tds_version=str(config.get("tds_version", "7.4")),
            )
            query_started = time.monotonic()
            cursor = connection.cursor()
            cursor.execute(str(config.get("query", "SELECT 1")))
            value = cursor.fetchone()
            cursor.close()
        else:
            client = MongoClient(
                host=host,
                port=port,
                username=username,
                password=password,
                authSource=str(config.get("auth_source", "admin")),
                serverSelectionTimeoutMS=timeout * 1000,
                connectTimeoutMS=timeout * 1000,
                tls=bool(config.get("use_tls", False)),
            )
            connection = client
            query_started = time.monotonic()
            response = client[database].command("ping")
            value = response.get("ok")

        query_time_ms = round((time.monotonic() - query_started) * 1000, 2)
        connection_time_ms = round((query_started - started) * 1000, 2)
        expected = config.get("expected_value")
        actual = value[0] if isinstance(value, tuple | list) and value else value
        ok = expected is None or str(actual) == str(expected)
        return _result(
            ok,
            started,
            metrics={
                "database_type": kind,
                "connection_time_ms": connection_time_ms,
                "query_time_ms": query_time_ms,
            },
            assertions=[
                {"type": "database_query", "success": ok, "expected": expected, "actual": actual}
            ],
            detail={
                "host": host,
                "port": port,
                "database": database,
                "query_time_ms": query_time_ms,
            },
            error_type=None if ok else "ASSERTION_FAILED",
            error_summary=None if ok else "数据库查询结果与期望值不一致",
        )
    except ValueError as e:
        return _result(False, started, error_type="INVALID_TARGET", error_summary=str(e))
    except (TimeoutError, ServerSelectionTimeoutError) as e:
        return _result(False, started, error_type="CONNECT_TIMEOUT", error_summary=str(e)[:300])
    except (PermissionError, OperationFailure) as e:
        return _result(False, started, error_type="AUTH_ERROR", error_summary=str(e)[:300])
    except (ConnectionRefusedError, ConnectionFailure) as e:
        return _result(False, started, error_type="CONNECT_REFUSED", error_summary=str(e)[:300])
    except Exception as e:
        message = str(e)[:300]
        lowered = message.lower()
        authentication_errors = ("password", "authentication", "login failed")
        error_type = (
            "AUTH_ERROR" if any(x in lowered for x in authentication_errors) else "PROBE_ERROR"
        )
        return _result(False, started, error_type=error_type, error_summary=message)
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def execute_probe(kind, target, config=None):
    config = config or {}
    return {
        "HTTP": http_probe,
        "API": http_probe,
        "TCP": tcp_probe,
        "DNS": dns_probe,
        "SSL": ssl_probe,
        "PING": ping_probe,
        "MSSQL": lambda target, config: database_probe("MSSQL", target, config),
        "POSTGRESQL": lambda target, config: database_probe("POSTGRESQL", target, config),
        "MYSQL": lambda target, config: database_probe("MYSQL", target, config),
        "MONGODB": lambda target, config: database_probe("MONGODB", target, config),
    }.get(
        kind,
        lambda *_: _result(
            False, time.monotonic(), error_type="INVALID_TARGET", error_summary="未知探测类型"
        ),
    )(target, config)
