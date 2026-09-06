#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_DIR}/.env"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"

cd "${PROJECT_DIR}"

usage() {
  cat <<'EOF'
用法: ./scripts/app.sh <命令> [服务名]

命令:
  start       构建镜像并启动全部服务，随后执行健康检查
  stop        停止并移除应用容器和网络（保留数据库、Redis 数据卷）
  restart     重新创建并启动全部服务，随后执行健康检查
  update      重新构建并滚动更新全部服务，随后执行健康检查
  status      显示各服务运行状态
  logs        实时查看日志；可追加服务名，例如 logs backend
  health      检查容器状态及 HTTP 存活、就绪接口
  config      校验 Docker Compose 配置
  help        显示帮助

说明: 本脚本不会删除 PostgreSQL 和 Redis 数据卷。
EOF
}

die() {
  echo "错误: $*" >&2
  exit 1
}

require_runtime() {
  command -v docker >/dev/null 2>&1 || die "未安装 Docker"
  docker compose version >/dev/null 2>&1 || die "未安装 Docker Compose 插件"
  [[ -f "${COMPOSE_FILE}" ]] || die "缺少 ${COMPOSE_FILE}"
  [[ -f "${ENV_FILE}" ]] || die "缺少 .env，请先执行: cp .env.example .env 并修改配置"
}

compose() {
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}

port_from_env() {
  local value
  value="$(sed -n 's/^NGINX_PORT=//p' "${ENV_FILE}" | tail -n 1 | tr -d '\r')"
  echo "${value:-80}"
}

health_check() {
  local port base_url attempt
  port="$(port_from_env)"
  base_url="http://127.0.0.1:${port}"

  echo "等待应用就绪: ${base_url}"
  for attempt in $(seq 1 60); do
    if curl --fail --silent --show-error --max-time 5 "${base_url}/health/live" >/dev/null \
      && curl --fail --silent --show-error --max-time 5 "${base_url}/health/ready" >/dev/null; then
      echo "健康检查通过: live=ok, ready=ok"
      compose ps
      return 0
    fi
    sleep 2
  done

  echo "健康检查失败，当前服务状态如下:" >&2
  compose ps >&2
  echo "最近后端与网关日志:" >&2
  compose logs --tail=80 backend nginx >&2
  return 1
}

command_name="${1:-help}"
service_name="${2:-}"

case "${command_name}" in
  help|-h|--help)
    usage
    ;;
  start)
    require_runtime
    compose config --quiet
    compose up -d --build
    health_check
    ;;
  stop)
    require_runtime
    compose down --remove-orphans
    echo "应用已停止，持久化数据卷已保留。"
    ;;
  restart)
    require_runtime
    compose config --quiet
    compose up -d --build --force-recreate
    health_check
    ;;
  update)
    require_runtime
    compose config --quiet
    compose build --pull
    compose up -d --remove-orphans
    health_check
    ;;
  status)
    require_runtime
    compose ps
    ;;
  logs)
    require_runtime
    if [[ -n "${service_name}" ]]; then
      compose logs --tail=200 -f "${service_name}"
    else
      compose logs --tail=200 -f
    fi
    ;;
  health)
    require_runtime
    health_check
    ;;
  config)
    require_runtime
    compose config --quiet
    echo "Docker Compose 配置校验通过。"
    ;;
  *)
    usage >&2
    die "未知命令: ${command_name}"
    ;;
esac
