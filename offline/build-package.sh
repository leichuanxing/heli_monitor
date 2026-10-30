#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "$PROJECT_DIR/VERSION")"
[[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'VERSION 格式无效' >&2; exit 1; }
OUTPUT_FILE="${1:-$PROJECT_DIR/heli-monitor-offline-${VERSION}-el9-x86_64.tar.gz}"
mkdir -p "$SCRIPT_DIR/packages"
for file in images/heli-monitor-images.tar.gz docker/docker-ce-el9-x86_64-rpms.tar.gz images/manifest.txt; do [[ -s "$SCRIPT_DIR/$file" ]] || { echo "缺少离线组件：$file" >&2; exit 1; }; done
printf '[1/4] 封装 %s 源码（排除密钥、缓存、依赖和运行数据）\n' "$VERSION"
tar --exclude='node_modules' --exclude='dist' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='.ruff_cache' --exclude='*.pyc' --exclude='*.tsbuildinfo' --exclude='*.log' --exclude='*.backup.*' --exclude='.env' --exclude='.env.local' --exclude='.env.production' --exclude='db.sqlite3' -czf "$SCRIPT_DIR/packages/heli-monitor-code.tar.gz" -C "$PROJECT_DIR" backend frontend deploy scripts docs docker-compose.offline.yml README.md .env.example VERSION
printf '[2/4] 校验脚本并记录组件版本\n'
for script in "$SCRIPT_DIR"/*.sh; do bash -n "$script"; done
cp "$PROJECT_DIR/VERSION" "$SCRIPT_DIR/VERSION"
printf '[3/4] 生成所有离线组件的 SHA-256\n'
(cd "$SCRIPT_DIR" && find . -type d -name __pycache__ -prune -o -type f ! -name checksums.sha256 -print0 | sort -z | xargs -0 sha256sum > checksums.sha256)
printf '[4/4] 生成完整离线包\n'
tar --exclude='__pycache__' --exclude='*.pyc' -czf "$OUTPUT_FILE" -C "$PROJECT_DIR" offline
(cd "$(dirname -- "$OUTPUT_FILE")" && sha256sum "$(basename -- "$OUTPUT_FILE")" > "$(basename -- "$OUTPUT_FILE").sha256")
printf '部署包：%s\n校验文件：%s.sha256\n' "$OUTPUT_FILE" "$OUTPUT_FILE"
