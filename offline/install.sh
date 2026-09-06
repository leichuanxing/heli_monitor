#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_ARCHIVE="$SCRIPT_DIR/images/heli-monitor-images.tar.gz"
CODE_ARCHIVE="$SCRIPT_DIR/packages/heli-monitor-code.tar.gz"
DOCKER_ARCHIVE="$SCRIPT_DIR/docker/docker-ce-el9-x86_64-rpms.tar.gz"

log() { printf '\n[heli-monitor] %s\n' "$*"; }
fail() { printf '\n[heli-monitor] ERROR: %s\n' "$*" >&2; exit 1; }

prompt_value() {
  local variable_name="$1" prompt_text="$2" default_value="$3" current_value input_value
  current_value="${!variable_name:-}"
  if [[ -n "$current_value" ]]; then
    printf -v "$variable_name" '%s' "$current_value"
    return
  fi
  if [[ ! -t 0 ]]; then
    printf -v "$variable_name" '%s' "$default_value"
    return
  fi
  read -r -p "$prompt_text [$default_value]: " input_value
  printf -v "$variable_name" '%s' "${input_value:-$default_value}"
}

collect_install_settings() {
  [[ -t 0 ]] || {
    [[ -n "${ADMIN_USERNAME:-}" ]] || fail "非交互安装必须设置 ADMIN_USERNAME"
    [[ -n "${ADMIN_PASSWORD:-}" ]] || fail "非交互安装必须设置 ADMIN_PASSWORD"
  }

  printf '\n合力数据业务监控系统安装向导\n'
  printf '%s\n' '--------------------------------'
  prompt_value ADMIN_USERNAME "系统管理用户名" "admin"
  [[ "$ADMIN_USERNAME" =~ ^[A-Za-z0-9_.@+-]{1,150}$ ]] || \
    fail "系统管理用户名格式不正确"

  if [[ -z "${ADMIN_PASSWORD:-}" ]]; then
    while true; do
      read -r -s -p "系统管理密码（至少 8 位）: " ADMIN_PASSWORD
      printf '\n'
      [[ "${#ADMIN_PASSWORD}" -ge 8 ]] || { printf '密码长度不能少于 8 位，请重新输入。\n'; continue; }
      read -r -s -p "再次输入系统管理密码: " admin_password_confirm
      printf '\n'
      [[ "$ADMIN_PASSWORD" == "$admin_password_confirm" ]] || {
        printf '两次输入的密码不一致，请重新输入。\n'
        continue
      }
      break
    done
  fi
  [[ "${#ADMIN_PASSWORD}" -ge 8 ]] || fail "系统管理密码长度不能少于 8 位"

  prompt_value ADMIN_EMAIL "系统管理员邮箱（可留空）" ""
  prompt_value NGINX_PORT "业务访问端口" "80"
  [[ "$NGINX_PORT" =~ ^[0-9]+$ ]] && (( NGINX_PORT >= 1 && NGINX_PORT <= 65535 )) || \
    fail "业务访问端口必须为 1-65535 的整数"

  prompt_value INSTALL_DIR "应用部署目录" "/opt/heli_monitor"
  [[ "$INSTALL_DIR" == /* ]] || fail "应用安装目录必须使用绝对路径"
  [[ "$INSTALL_DIR" != "/" ]] || fail "不能将应用直接安装到根目录"
  INSTALL_DIR="${INSTALL_DIR%/}"

  printf '\n安装配置确认：\n'
  printf '  系统管理用户：%s\n' "$ADMIN_USERNAME"
  printf '  管理员邮箱：  %s\n' "${ADMIN_EMAIL:-未设置}"
  printf '  业务访问端口：%s\n' "$NGINX_PORT"
  printf '  应用安装目录：%s\n' "$INSTALL_DIR"
  if [[ -t 0 ]]; then
    read -r -p "确认开始安装？[Y/n]: " install_confirm
    [[ "${install_confirm:-Y}" =~ ^[Yy]$ ]] || fail "用户取消安装"
  fi
}

[[ "$(uname -s)" == "Linux" ]] || fail "仅支持 Linux 服务器"
[[ "$(id -u)" -eq 0 ]] || fail "请使用 root 用户或 sudo 执行"
command -v openssl >/dev/null 2>&1 || fail "未检测到 openssl"
[[ -f "$IMAGE_ARCHIVE" ]] || fail "缺少镜像归档：$IMAGE_ARCHIVE"
[[ -f "$CODE_ARCHIVE" ]] || fail "缺少代码归档：$CODE_ARCHIVE"

collect_install_settings

install_docker_if_needed() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    log "已检测到 Docker Engine 和 Docker Compose，跳过安装"
    systemctl enable --now docker >/dev/null 2>&1 || fail "Docker 服务启动失败"
    docker info >/dev/null 2>&1 || fail "Docker 服务不可用"
    return
  fi

  log "未检测到完整的 Docker 环境，开始离线安装"
  [[ "$(uname -m)" == "x86_64" ]] || fail "内置 Docker 离线包仅支持 x86_64"
  [[ -r /etc/os-release ]] || fail "无法识别操作系统"
  # shellcheck disable=SC1091
  source /etc/os-release
  os_family="${ID:-} ${ID_LIKE:-}"
  [[ "$os_family" =~ (rhel|centos|fedora|rocky|almalinux) ]] || \
    fail "内置 Docker 离线包仅支持 RHEL 9 兼容发行版"
  [[ "${VERSION_ID%%.*}" == "9" ]] || fail "内置 Docker 离线包仅支持 EL9"
  command -v dnf >/dev/null 2>&1 || fail "未检测到 dnf 包管理器"
  [[ -f "$DOCKER_ARCHIVE" ]] || fail "缺少 Docker 离线安装包：$DOCKER_ARCHIVE"

  docker_rpm_tmp="$(mktemp -d /tmp/heli-docker-rpms.XXXXXX)"
  tar -xzf "$DOCKER_ARCHIVE" -C "$docker_rpm_tmp"
  mapfile -t docker_rpms < <(find "$docker_rpm_tmp" -type f -name '*.rpm' -print)
  [[ "${#docker_rpms[@]}" -gt 0 ]] || fail "Docker 离线安装包中没有 RPM 文件"
  dnf install -y --disablerepo='*' --allowerasing "${docker_rpms[@]}" || \
    fail "Docker 离线 RPM 安装失败"
  rm -rf -- "$docker_rpm_tmp"

  systemctl daemon-reload
  systemctl enable --now docker || fail "Docker 服务启动失败"
  docker info >/dev/null 2>&1 || fail "Docker Engine 安装后不可用"
  docker compose version >/dev/null 2>&1 || fail "Docker Compose 安装后不可用"
  log "Docker Engine 和 Docker Compose 离线安装完成"
}

if [[ -f "$SCRIPT_DIR/checksums.sha256" ]]; then
  log "校验安装包完整性"
  (cd "$SCRIPT_DIR" && sha256sum -c checksums.sha256) || fail "安装包校验失败"
fi

install_docker_if_needed

log "加载离线 Docker 镜像（耗时取决于磁盘速度）"
gzip -dc "$IMAGE_ARCHIVE" | docker load

log "安装应用代码到 $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
tar -xzf "$CODE_ARCHIVE" -C "$INSTALL_DIR"
chmod +x "$INSTALL_DIR/scripts/app.sh" 2>/dev/null || true

ENV_FILE="$INSTALL_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  SERVER_IP="${SERVER_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
  SERVER_IP="${SERVER_IP:-127.0.0.1}"
  DJANGO_SECRET_KEY="$(openssl rand -hex 48)"
  POSTGRES_PASSWORD="$(openssl rand -hex 24)"
  SECRET_ENCRYPTION_KEY="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n')"
  cat >"$ENV_FILE" <<EOF
APP_ENV=production
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=$DJANGO_SECRET_KEY
ALLOWED_HOSTS=localhost,127.0.0.1,$SERVER_IP
CSRF_TRUSTED_ORIGINS=http://$SERVER_IP:$NGINX_PORT
POSTGRES_DB=business_monitor
POSTGRES_USER=business_monitor
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
DATABASE_URL=postgresql://business_monitor:$POSTGRES_PASSWORD@postgres:5432/business_monitor
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
SECRET_ENCRYPTION_KEY=$SECRET_ENCRYPTION_KEY
JWT_ACCESS_MINUTES=15
JWT_REFRESH_DAYS=7
DEFAULT_TIME_ZONE=Asia/Shanghai
MONITOR_RESULT_RETENTION_COUNT=10000
ALLOWED_PROBE_CIDRS=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
BLOCKED_PROBE_PORTS=25,445
NGINX_PORT=$NGINX_PORT
EOF
  chmod 600 "$ENV_FILE"
else
  log "保留现有环境配置 $ENV_FILE"
fi

cd "$INSTALL_DIR"
COMPOSE=(docker compose -f docker-compose.offline.yml --env-file .env)
log "校验离线编排配置"
"${COMPOSE[@]}" config --quiet

log "停止可能存在的旧版应用容器"
"${COMPOSE[@]}" stop nginx backend worker beat frontend >/dev/null 2>&1 || true

wait_for_service_health() {
  local service_name="$1" max_attempts="$2" container_id health_status
  for _ in $(seq 1 "$max_attempts"); do
    container_id="$("${COMPOSE[@]}" ps -q "$service_name")"
    if [[ -n "$container_id" ]]; then
      health_status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
      [[ "$health_status" == "healthy" ]] && return 0
      if [[ "$health_status" == "exited" || "$health_status" == "dead" ]]; then
        return 1
      fi
    fi
    sleep 3
  done
  return 1
}

log "启动 PostgreSQL 和 Redis"
"${COMPOSE[@]}" up -d --remove-orphans postgres redis
wait_for_service_health postgres 60 || {
  "${COMPOSE[@]}" logs --tail=120 postgres
  fail "PostgreSQL 未能正常启动"
}
wait_for_service_health redis 60 || {
  "${COMPOSE[@]}" logs --tail=120 redis
  fail "Redis 未能正常启动"
}

log "同步 PostgreSQL 账号密码（兼容已有数据卷）"
if ! "${COMPOSE[@]}" exec -T postgres sh -ec '
  psql --set=ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set=new_password="$POSTGRES_PASSWORD" <<'"'"'SQL'"'"'
ALTER ROLE CURRENT_USER WITH PASSWORD :'"'"'new_password'"'"';
SQL
'; then
  "${COMPOSE[@]}" logs --tail=120 postgres
  fail "PostgreSQL 账号密码同步失败"
fi

log "执行数据库迁移（以下为 Django 迁移过程）"
if ! "${COMPOSE[@]}" run --rm --no-deps backend \
  python manage.py migrate --noinput --verbosity 2; then
  fail "数据库迁移失败"
fi
log "数据库迁移完成"

log "收集后端静态资源"
if ! "${COMPOSE[@]}" run --rm --no-deps backend \
  python manage.py collectstatic --noinput --verbosity 1; then
  fail "后端静态资源收集失败"
fi

log "启动后端服务"
"${COMPOSE[@]}" up -d backend worker beat
if ! wait_for_service_health backend 120; then
  "${COMPOSE[@]}" ps -a
  "${COMPOSE[@]}" logs --tail=200 backend
  fail "后端服务启动失败，请根据以上日志排查"
fi

log "启动前端和网关"
"${COMPOSE[@]}" up -d frontend
wait_for_service_health frontend 60 || {
  "${COMPOSE[@]}" logs --tail=120 frontend
  fail "前端服务未能正常启动"
}
"${COMPOSE[@]}" up -d nginx

log "等待应用健康检查"
ready=0
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${NGINX_PORT}/health/ready" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 3
done
[[ "$ready" -eq 1 ]] || { "${COMPOSE[@]}" ps; fail "应用未在规定时间内就绪"; }

log "创建或更新系统管理员账号"
"${COMPOSE[@]}" exec -T \
  -e ADMIN_USERNAME="$ADMIN_USERNAME" \
  -e ADMIN_EMAIL="${ADMIN_EMAIL:-}" \
  -e ADMIN_PASSWORD="$ADMIN_PASSWORD" backend \
  python manage.py shell -c \
  'import os; from django.contrib.auth import get_user_model; U=get_user_model(); u,_=U.objects.get_or_create(username=os.environ["ADMIN_USERNAME"]); u.email=os.environ.get("ADMIN_EMAIL",""); u.is_staff=True; u.is_superuser=True; u.is_active=True; u.set_password(os.environ["ADMIN_PASSWORD"]); u.save()'

log "安装完成"
printf '访问地址：http://%s:%s/\n' "${SERVER_IP:-127.0.0.1}" "$NGINX_PORT"
printf '管理命令：INSTALL_DIR=%q %q status\n' "$INSTALL_DIR" "$SCRIPT_DIR/manage.sh"
