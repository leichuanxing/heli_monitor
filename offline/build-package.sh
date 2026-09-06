#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "$PROJECT_DIR/VERSION")"
[[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { printf 'ERROR: VERSION 格式无效\n' >&2; exit 1; }
OUTPUT_FILE="${1:-$PROJECT_DIR/heli-monitor-offline-${VERSION}-el9-x86_64.tar.gz}"
IMAGE_ARCHIVE="$SCRIPT_DIR/images/heli-monitor-images.tar.gz"
DOCKER_ARCHIVE="$SCRIPT_DIR/docker/docker-ce-el9-x86_64-rpms.tar.gz"
CODE_ARCHIVE="$SCRIPT_DIR/packages/heli-monitor-code.tar.gz"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
command -v tar >/dev/null 2>&1 || fail "未检测到 tar"
command -v sha256sum >/dev/null 2>&1 || fail "未检测到 sha256sum"
[[ -f "$IMAGE_ARCHIVE" ]] || fail "缺少离线镜像：$IMAGE_ARCHIVE"
[[ -f "$DOCKER_ARCHIVE" ]] || fail "缺少 Docker RPM 包：$DOCKER_ARCHIVE"

printf '[1/4] 封装当前应用代码\n'
tar -czf "$CODE_ARCHIVE" -C "$PROJECT_DIR" \
  backend frontend deploy scripts docker-compose.offline.yml README.md .env.example VERSION

printf '[2/4] 生成组件清单\n'
{
  printf '离线镜像归档：heli-monitor-images.tar.gz\n'
  printf '包含镜像：postgres:16-alpine, redis:7-alpine, nginx:1.27-alpine, '
  printf 'heli-monitor-backend:latest, heli-monitor-worker:latest, '
  printf 'heli-monitor-beat:latest, heli-monitor-frontend:latest\n'
} > "$SCRIPT_DIR/images/manifest.txt"

printf '[3/4] 生成 SHA-256 校验文件\n'
(
  cd "$SCRIPT_DIR"
  sha256sum \
    images/heli-monitor-images.tar.gz \
    packages/heli-monitor-code.tar.gz \
    docker/docker-ce-el9-x86_64-rpms.tar.gz > checksums.sha256
)

printf '[4/4] 生成完整离线部署包\n'
tar -czf "$OUTPUT_FILE" -C "$PROJECT_DIR" offline
(
  cd "$(dirname "$OUTPUT_FILE")"
  sha256sum "$(basename "$OUTPUT_FILE")" > "$(basename "$OUTPUT_FILE").sha256"
)
printf '完成：%s\n' "$OUTPUT_FILE"
printf '校验：%s.sha256\n' "$OUTPUT_FILE"
