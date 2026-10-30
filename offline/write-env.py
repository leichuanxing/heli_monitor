import base64
import hashlib
import ipaddress
import os
import re
import secrets
import socket
import subprocess
import sys
from pathlib import Path

path, data_dir, port, tag = sys.argv[1:]
server = os.environ.get("SERVER_IP", "")
if not server:
    try:
        addresses = subprocess.check_output(["hostname", "-I"], text=True).split()
        server = next((value for value in addresses if ipaddress.ip_address(value).version == 4), "127.0.0.1")
    except (OSError, ValueError, subprocess.SubprocessError):
        server = "127.0.0.1"
if not re.fullmatch(r"[A-Za-z0-9.-]+", server):
    raise SystemExit("SERVER_IP 必须为 IPv4 地址或域名")
project = "heli-monitor-" + hashlib.sha256(data_dir.encode()).hexdigest()[:12]
password = secrets.token_hex(24)
hostname = socket.gethostname()
if not re.fullmatch(r"[A-Za-z0-9.-]+", hostname):
    hostname = "localhost"
values = {
    "APP_ENV": "production", "DJANGO_DEBUG": "false",
    "DJANGO_SECRET_KEY": secrets.token_hex(48),
    "SECRET_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    "POSTGRES_DB": "business_monitor", "POSTGRES_USER": "business_monitor",
    "POSTGRES_PASSWORD": password,
    "DATABASE_URL": f"postgresql://business_monitor:{password}@postgres:5432/business_monitor",
    "REDIS_URL": "redis://redis:6379/0", "CELERY_BROKER_URL": "redis://redis:6379/1",
    "CELERY_RESULT_BACKEND": "redis://redis:6379/2",
    "ALLOWED_HOSTS": f"localhost,127.0.0.1,{hostname},{server}",
    "CSRF_TRUSTED_ORIGINS": f"http://{server}:{port}",
    "JWT_ACCESS_MINUTES": "15", "JWT_REFRESH_DAYS": "7", "DEFAULT_TIME_ZONE": "Asia/Shanghai",
    "MONITOR_RESULT_RETENTION_COUNT": "10000",
    "ALLOWED_PROBE_CIDRS": "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
    "BLOCKED_PROBE_PORTS": "25,445", "NGINX_PORT": port,
    "DATA_DIR": data_dir, "COMPOSE_PROJECT_NAME": project, "IMAGE_TAG": tag,
}
fd = os.open(Path(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as stream:
    for key, value in values.items():
        stream.write(f"{key}={value}\n")
print("独立应用配置已生成，权限 0600；登录密码未写入配置")
