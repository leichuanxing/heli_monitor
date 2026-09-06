#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/heli_monitor}"
[[ -d "$INSTALL_DIR" ]] || { echo "安装目录不存在：$INSTALL_DIR" >&2; exit 1; }
cd "$INSTALL_DIR"
COMPOSE=(docker compose -f docker-compose.offline.yml --env-file .env)
ACTION="${1:-status}"

case "$ACTION" in
  start) "${COMPOSE[@]}" up -d ;;
  stop) "${COMPOSE[@]}" stop ;;
  restart) "${COMPOSE[@]}" restart ;;
  status) "${COMPOSE[@]}" ps ;;
  health)
    PORT="$(sed -n 's/^NGINX_PORT=//p' .env | tail -1)"; PORT="${PORT:-80}"
    curl -fsS "http://127.0.0.1:${PORT}/health/ready" && echo
    ;;
  logs)
    if [[ -n "${2:-}" ]]; then
      "${COMPOSE[@]}" logs -f --tail=300 "$2"
    else
      "${COMPOSE[@]}" logs -f --tail=300
    fi
    ;;
  create-admin) "${COMPOSE[@]}" exec backend python manage.py createsuperuser ;;
  backup)
    mkdir -p backups
    FILE="backups/heli-monitor-$(date +%Y%m%d-%H%M%S).sql.gz"
    DB_USER="$(sed -n 's/^POSTGRES_USER=//p' .env | tail -1)"
    DB_NAME="$(sed -n 's/^POSTGRES_DB=//p' .env | tail -1)"
    "${COMPOSE[@]}" exec -T postgres pg_dump -U "${DB_USER:-business_monitor}" "${DB_NAME:-business_monitor}" | gzip >"$FILE"
    chmod 600 "$FILE"
    echo "备份完成：$INSTALL_DIR/$FILE"
    ;;
  *) echo "用法：$0 {start|stop|restart|status|health|logs [service]|create-admin|backup}" >&2; exit 2 ;;
esac
