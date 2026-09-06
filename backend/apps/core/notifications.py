import base64
import hashlib
import hmac
import re
import smtplib
import time
from email.message import EmailMessage
from urllib.parse import quote_plus, urlparse

import httpx

from .probes import validate_target


def _required(config, *names):
    missing = [name for name in names if not config.get(name)]
    if missing:
        raise ValueError(f"缺少配置：{', '.join(missing)}")


def _validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Webhook URL 无效")
    validate_target(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))


def _email(config, subject, content):
    _required(config, "host", "from_email", "recipients")
    recipients = config["recipients"]
    if isinstance(recipients, str):
        recipients = [x.strip() for x in recipients.split(",") if x.strip()]
    if not recipients:
        raise ValueError("收件人不能为空")
    port = int(config.get("port", 465 if config.get("use_ssl") else 587))
    validate_target(config["host"], port)
    message = EmailMessage()
    message["Subject"], message["From"], message["To"] = (
        subject,
        config["from_email"],
        ", ".join(recipients),
    )
    message.set_content(content)
    smtp_cls = smtplib.SMTP_SSL if config.get("use_ssl") else smtplib.SMTP
    with smtp_cls(config["host"], port, timeout=float(config.get("timeout", 10))) as smtp:
        if config.get("use_tls") and not config.get("use_ssl"):
            smtp.starttls()
        if config.get("username"):
            _required(config, "password")
            smtp.login(config["username"], config["password"])
        smtp.send_message(message)
    return {"recipient": ", ".join(recipients)}


def _post(url, payload, config):
    _validate_url(url)
    response = httpx.post(
        url,
        json=payload,
        headers=config.get("headers", {}),
        timeout=float(config.get("timeout", 10)),
    )
    response.raise_for_status()
    data = response.json() if "json" in response.headers.get("content-type", "") else {}
    error_code = data.get("errcode", data.get("code", 0))
    if error_code not in (0, "0", None):
        raise RuntimeError(
            data.get("errmsg") or data.get("message") or f"渠道返回错误 {error_code}"
        )
    return {"status_code": response.status_code}


def _wechat(config, subject, content):
    _required(config, "webhook_url")
    return _post(
        config["webhook_url"],
        {"msgtype": "text", "text": {"content": f"{subject}\n{content}"}},
        config,
    )


def _dingtalk(config, subject, content):
    _required(config, "webhook_url")
    url = config["webhook_url"]
    if config.get("secret"):
        timestamp = str(round(time.time() * 1000))
        signature = quote_plus(
            base64.b64encode(
                hmac.new(
                    config["secret"].encode(),
                    f"{timestamp}\n{config['secret']}".encode(),
                    hashlib.sha256,
                ).digest()
            )
        )
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}timestamp={timestamp}&sign={signature}"
    return _post(url, {"msgtype": "text", "text": {"content": f"{subject}\n{content}"}}, config)


def _webhook(config, subject, content):
    _required(config, "url")
    return _post(
        config["url"],
        {
            "event": "channel.test",
            "title": subject,
            "content": content,
            "timestamp": int(time.time()),
        },
        config,
    )


def _serverchan(config, subject, content):
    _required(config, "sendkey")
    sendkey = str(config["sendkey"]).strip()
    if sendkey.startswith("sctp"):
        match = re.match(r"^sctp(\d+)t", sendkey)
        if not match:
            raise ValueError("Server酱³ SendKey 格式无效")
        base_url = f"https://{match.group(1)}.push.ft07.com/send"
    else:
        base_url = "https://sctapi.ftqq.com"
    payload = {"title": subject, "desp": content}
    for key in ("tags", "short", "channel", "openid"):
        if config.get(key) not in (None, ""):
            payload[key] = config[key]
    if config.get("noip"):
        payload["noip"] = "1"
    response = httpx.post(
        f"{base_url}/{sendkey}.send",
        data=payload,
        timeout=float(config.get("timeout", 10)),
    )
    response.raise_for_status()
    result = response.json()
    code = result.get("code", result.get("errno", 0))
    if code not in (0, "0", None):
        raise RuntimeError(
            result.get("message") or result.get("errmsg") or f"Server酱返回错误 {code}"
        )
    data = result.get("data") or {}
    return {
        "status_code": response.status_code,
        "pushid": data.get("pushid") if isinstance(data, dict) else None,
    }


def send_notification(channel, subject, content):
    started = time.monotonic()
    try:
        handler = {
            "EMAIL": _email,
            "WECHAT": _wechat,
            "DINGTALK": _dingtalk,
            "WEBHOOK": _webhook,
            "SERVERCHAN": _serverchan,
        }.get(channel.channel_type)
        if not handler:
            raise ValueError("不支持的通知渠道类型")
        detail = handler(channel.config or {}, subject, content)
        return {
            "success": True,
            "message": "消息发送成功",
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
            "detail": detail,
        }
    except Exception as exc:
        return {
            "success": False,
            "message": _safe_error(exc, channel.config or {}),
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
            "detail": {},
        }


def _safe_error(exc, config):
    message = str(exc)

    def redact(values):
        nonlocal message
        for key, value in values.items():
            if isinstance(value, dict):
                redact(value)
            elif value and any(word in key.lower() for word in (
                "password", "secret", "token", "key", "authorization", "url"
            )):
                message = message.replace(str(value), "[已隐藏]")

    redact(config)
    message = re.sub(r"https?://[^\s\"'<>]+", "[渠道地址已隐藏]", message)
    return message[:500]


def send_test_notification(channel):
    return send_notification(
        channel,
        "[HELI MONITOR] 通知渠道测试",
        f"渠道“{channel.name}”测试成功。收到此消息表示通知链路可用。",
    )
