"""Set a fresh Docker installation's data-root while preserving other daemon options."""
import json
import os
import sys
from pathlib import Path

path = Path("/etc/docker/daemon.json")
root = Path(sys.argv[1]).resolve()
settings = json.loads(path.read_text()) if path.exists() else {}
if not isinstance(settings, dict):
    raise SystemExit("daemon.json 必须是 JSON 对象")
previous = Path(settings.get("data-root", "/var/lib/docker")).resolve()
if previous != root and previous.exists() and any(previous.iterdir()):
    raise SystemExit("检测到旧 Docker 数据；请先人工规划迁移，本安装器不会搬动或覆盖旧数据")
settings["data-root"] = str(root)
temporary = path.with_name("daemon.json.heli-tmp")
fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as stream:
    json.dump(settings, stream, indent=2)
    stream.write("\n")
os.replace(temporary, path)
print("Docker 存储目录配置完成：" + str(root))
