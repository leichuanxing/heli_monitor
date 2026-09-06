import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

PREFIX = "fernet:v1:"


def _cipher():
    configured = str(getattr(settings, "SECRET_ENCRYPTION_KEY", "")).strip()
    if configured:
        # Accept either a native Fernet key or an operator-friendly passphrase.
        # Deployment secrets are often arbitrary strings; derive a stable valid
        # Fernet key instead of failing while saving a monitor.
        try:
            decoded = base64.urlsafe_b64decode(configured.encode())
        except (ValueError, TypeError):
            decoded = b""
        key = (
            configured.encode()
            if len(decoded) == 32
            else base64.urlsafe_b64encode(hashlib.sha256(configured.encode()).digest())
        )
    else:
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt_secret(value):
    value = str(value or "")
    if not value or value.startswith(PREFIX):
        return value
    return PREFIX + _cipher().encrypt(value.encode()).decode()


def decrypt_secret(value):
    value = str(value or "")
    if not value.startswith(PREFIX):
        return value
    try:
        return _cipher().decrypt(value.removeprefix(PREFIX).encode()).decode()
    except InvalidToken as exc:
        raise ValueError("数据库探测密码无法解密，请重新保存任务密码") from exc
