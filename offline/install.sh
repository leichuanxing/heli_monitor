#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_ARCHIVE="$SCRIPT_DIR/images/heli-monitor-images.tar.gz"
CODE_ARCHIVE="$SCRIPT_DIR/packages/heli-monitor-code.tar.gz"
DOCKER_ARCHIVE="$SCRIPT_DIR/docker/docker-ce-el9-x86_64-rpms.tar.gz"
IMAGE_TAG="v1.0.3"
LOG_FILE=""
TEMP_DIR=""
CURRENT_STEP=0
INTERACTIVE=0

log() { printf '\n[heli-monitor] %s\n' "$*"; }
fail() { printf '\n[heli-monitor] ERROR: %s\n' "$*" >&2; return 1; }
step() { CURRENT_STEP="$1"; printf '\n[%s/10] %s\n' "$1" "$2"; }
cleanup() {
  if [[ -n "$TEMP_DIR" && "$TEMP_DIR" == /tmp/heli-monitor-install.* && -d "$TEMP_DIR" ]]; then rm -rf -- "$TEMP_DIR"; fi
  unset ADMIN_PASSWORD
}
on_error() {
  local code="$1" line="$2"
  trap - ERR
  printf '\n安装失败：阶段 %s/10，脚本行 %s，退出码 %s。\n' "$CURRENT_STEP" "$line" "$code" >&2
  [[ -z "$LOG_FILE" ]] || printf '安装日志：%s\n' "$LOG_FILE" >&2
  if declare -p COMPOSE >/dev/null 2>&1; then "${COMPOSE[@]}" ps -a || true; "${COMPOSE[@]}" logs --tail=80 || true; fi
  exit "$code"
}
prompt_value() {
  local variable="$1" message="$2" default="$3" input
  [[ -z "${!variable:-}" ]] || return 0
  if (( INTERACTIVE )); then read -r -p "$message [$default]: " input; else input=""; fi
  printf -v "$variable" '%s' "${input:-$default}"
}
normalize_dir() {
  local value="$1"
  [[ "$value" =~ ^/[A-Za-z0-9_./-]+$ && "$value" != *'/../'* && "$value" != */.. ]] || { fail "目录必须为绝对路径，限英文字母、数字、点、下划线、连字符和斜杠"; return 1; }
  value="$(readlink -m -- "$value")"
  [[ "$value" =~ ^/[A-Za-z0-9_./-]+$ ]] || { fail "实际目录包含不支持的字符"; return 1; }
  case "$value" in /|/etc|/etc/*|/usr|/usr/*|/bin|/sbin|/boot|/boot/*|/proc|/proc/*|/sys|/sys/*|/dev|/dev/*|/run|/run/*) fail "不能使用系统目录：$value"; return 1;; esac
  printf '%s' "$value"
}
validate_port() { [[ "$1" =~ ^[0-9]{1,5}$ ]] && (( 10#$1>=1 && 10#$1<=65535 )); }
collect_settings() {
  printf '\nHeli Monitor v1.0.3 离线安装向导\n'
  if (( ! ENGINE_PRESENT )); then prompt_value DOCKER_DATA_ROOT 'Docker 存储目录' '/var/lib/docker'; DOCKER_DATA_ROOT="$(normalize_dir "$DOCKER_DATA_ROOT")"; fi
  prompt_value DATA_DIR '数据持久化目录' '/opt/monitor'
  DATA_DIR="$(normalize_dir "$DATA_DIR")"
  [[ "$DATA_DIR" != /var/lib/docker && "$DATA_DIR" != /var/lib/docker/* ]] || fail '应用持久化目录不能放在 Docker 数据目录中'
  if [[ -n "${DOCKER_DATA_ROOT:-}" ]]; then
    [[ "$DATA_DIR/" != "$DOCKER_DATA_ROOT/"* && "$DOCKER_DATA_ROOT/" != "$DATA_DIR/"* ]] || fail 'Docker 与应用持久化目录不能相同或相互包含'
  fi
  prompt_value NGINX_PORT '应用访问端口' '80'
  validate_port "$NGINX_PORT" || fail '端口必须为 1-65535 的整数'
  NGINX_PORT="$((10#$NGINX_PORT))"
  prompt_value ADMIN_USERNAME '应用登录用户' 'admin'
  [[ "$ADMIN_USERNAME" =~ ^[A-Za-z0-9_.@+-]{1,150}$ ]] || fail '登录用户名格式无效'
  if [[ -z "${ADMIN_PASSWORD:-}" ]]; then
    (( INTERACTIVE )) || fail '非交互安装必须设置 ADMIN_PASSWORD'
    local confirm
    while true; do
      read -r -s -p '应用登录密码（至少 12 位，避免纯数字、常见密码及与账号相似）: ' ADMIN_PASSWORD; printf '\n'
      [[ ${#ADMIN_PASSWORD} -ge 12 ]] || { printf '密码不足 12 位，请重新输入。\n'; continue; }
      read -r -s -p '再次输入应用登录密码: ' confirm; printf '\n'
      [[ "$confirm" == "$ADMIN_PASSWORD" ]] && break
      printf '两次输入不一致，请重新输入。\n'
    done
  fi
  [[ ${#ADMIN_PASSWORD} -ge 12 ]] || fail '登录密码不足 12 位'
  INSTALL_DIR="$DATA_DIR/app"
  [[ ! -e "$INSTALL_DIR/.env" && ! -e "$DATA_DIR/postgres/PG_VERSION" ]] || fail '目录已有应用或数据库；为保护数据，本向导不覆盖已有安装，请使用原管理脚本或另选空目录'
  local existing
  for existing in "$INSTALL_DIR" "$DATA_DIR/postgres" "$DATA_DIR/redis"; do
    [[ ! -L "$existing" ]] || fail "数据子目录不能为符号链接：$existing"
    [[ ! -d "$existing" || -z "$(ls -A -- "$existing")" ]] || fail "目录非空，为保护数据拒绝覆盖：$existing"
  done
  for existing in "$DATA_DIR/logs" "$DATA_DIR/backups"; do [[ ! -L "$existing" ]] || fail "日志和备份目录不能为符号链接：$existing"; done
  [[ "$SCRIPT_DIR/" != "$DATA_DIR/"* ]] || fail '安装包不能放在选定的持久化目录内'
  printf '\n配置确认：\n  数据目录：%s\n  应用目录：%s\n  应用端口：%s\n  登录用户：%s\n  登录密码：已输入（日志不记录）\n' "$DATA_DIR" "$INSTALL_DIR" "$NGINX_PORT" "$ADMIN_USERNAME"
  if (( ENGINE_PRESENT )); then printf '  Docker：保留现有配置和存储目录\n'; else printf '  Docker 存储目录：%s\n' "$DOCKER_DATA_ROOT"; fi
  if (( INTERACTIVE )); then read -r -p '确认开始安装？[Y/n]: ' confirm; [[ "${confirm:-Y}" =~ ^[Yy]$ ]] || fail '安装已取消'; fi
}
install_docker() {
  if (( ENGINE_PRESENT )); then
    log '已检测到 Docker Engine，保留现有 daemon.json 和数据目录'
    systemctl start docker
    docker info >/dev/null
    if ! docker compose version >/dev/null 2>&1; then
      log '缺少 Compose 插件，安装离线插件（不更改 Docker 存储目录）'
      check_el9
      tar -xzf "$DOCKER_ARCHIVE" -C "$TEMP_DIR"
      local plugin
      plugin="$(find "$TEMP_DIR" -type f -name 'docker-compose-plugin-*.rpm' -print -quit)"
      [[ -n "$plugin" ]] || fail '离线包缺少 Compose 插件'
      dnf -y --disableplugin='*' --disablerepo='*' --setopt=install_weak_deps=False install "$plugin"
    fi
  else
    check_el9
    log '离线安装 Docker Engine、CLI、containerd、Buildx、Compose 及依赖'
    tar -xzf "$DOCKER_ARCHIVE" -C "$TEMP_DIR"
    local rpms=()
    mapfile -t rpms < <(find "$TEMP_DIR" -type f -name '*.rpm' -print)
    (( ${#rpms[@]}>0 )) || fail '离线 Docker 包没有 RPM 文件'
    dnf -y --disableplugin='*' --disablerepo='*' --setopt=install_weak_deps=False install "${rpms[@]}"
    mkdir -p /etc/docker "$DOCKER_DATA_ROOT"
    [[ ! -e /etc/docker/daemon.json ]] || cp -p /etc/docker/daemon.json "/etc/docker/daemon.json.before-heli-$(date +%Y%m%d-%H%M%S)"
    "$PYTHON" "$SCRIPT_DIR/configure-docker.py" "$DOCKER_DATA_ROOT"
    systemctl daemon-reload
    systemctl enable --now docker
  fi
  docker info >/dev/null
  docker compose version
  local actual_root
  actual_root="$(docker info --format '{{.DockerRootDir}}')"
  actual_root="$(readlink -m -- "$actual_root")"
  [[ "$DATA_DIR/" != "$actual_root/"* && "$actual_root/" != "$DATA_DIR/"* ]] || fail '应用目录与现有 Docker 存储目录冲突'
  log "Docker 数据目录：$(docker info --format '{{.DockerRootDir}}')"
}
check_el9() {
  local ID='' ID_LIKE='' VERSION_ID=''
  # shellcheck source=/dev/null
  source /etc/os-release
  [[ "${ID} ${ID_LIKE}" =~ (rhel|centos|rocky|almalinux) && "${VERSION_ID%%.*}" == 9 ]] || fail '内置 Docker RPM 仅支持 EL9 x86_64，请在匹配系统运行'
  command -v dnf >/dev/null || fail '未检测到 dnf'
}
wait_service() {
  local svc="$1" max="$2" id state health attempt
  for ((attempt=1;attempt<=max;attempt++)); do
    id="$("${COMPOSE[@]}" ps -q "$svc")"
    if [[ -n "$id" ]]; then
      state="$(docker inspect -f '{{.State.Status}}' "$id")"
      health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$id")"
      [[ "$health" == healthy ]] && return 0
      [[ "$state" != exited && "$state" != dead ]] || { fail "$svc 容器异常退出"; return 1; }
    fi
    (( attempt % 5 )) || printf '等待 %s 就绪……（%s/%s）\n' "$svc" "$attempt" "$max"
    sleep 3
  done
  fail "$svc 未在规定时间内就绪"
}
main() {
  trap 'on_error "$?" "$LINENO"' ERR
  trap cleanup EXIT
  [[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || fail '离线包仅支持 Linux x86_64'
  (( EUID==0 )) || fail '请使用 root 或 sudo bash install.sh'
  [[ -t 0 && -t 1 ]] && INTERACTIVE=1
  for tool in tar gzip sha256sum openssl curl readlink tee; do command -v "$tool" >/dev/null || fail "缺少基础工具：$tool"; done
  PYTHON="$(command -v python3 || true)"; [[ -n "$PYTHON" ]] || PYTHON=/usr/libexec/platform-python
  [[ -x "$PYTHON" ]] || fail '需要 Python 3（EL9 默认提供），请安装对应系统基础包'
  ENGINE_PRESENT=0
  if command -v docker >/dev/null 2>&1 && { command -v dockerd >/dev/null 2>&1 || systemctl cat docker.service >/dev/null 2>&1; }; then ENGINE_PRESENT=1; fi
  log "Docker 检测完成：$([[ "$ENGINE_PRESENT" == 1 ]] && echo 已安装 || echo 未安装)"
  collect_settings
  mkdir -p "$DATA_DIR/logs"
  LOG_FILE="$DATA_DIR/logs/install-$(date +%Y%m%d-%H%M%S).log"
  touch "$LOG_FILE"; chmod 600 "$LOG_FILE"
  exec > >(tee -a "$LOG_FILE") 2>&1
  TEMP_DIR="$(mktemp -d /tmp/heli-monitor-install.XXXXXX)"
  step 1 '校验离线包与目标目录'
  [[ -f "$SCRIPT_DIR/checksums.sha256" ]] || fail '缺少 checksums.sha256'
  (cd "$SCRIPT_DIR" && sha256sum --strict -c checksums.sha256)
  "$PYTHON" "$SCRIPT_DIR/check-port.py" "$NGINX_PORT"
  step 2 '准备 Docker 运行环境'
  install_docker
  step 3 '导入 v1.0.3 应用镜像（无网络拉取）'
  gzip -dc "$IMAGE_ARCHIVE" | docker load
  for image in postgres:16-alpine redis:7-alpine nginx:1.27-alpine heli-monitor-backend:$IMAGE_TAG heli-monitor-worker:$IMAGE_TAG heli-monitor-beat:$IMAGE_TAG heli-monitor-frontend:$IMAGE_TAG; do docker image inspect "$image" >/dev/null; done
  step 4 '校验登录密码并写入应用配置'
  export ADMIN_USERNAME ADMIN_PASSWORD
  "$PYTHON" -c 'import json,os,sys; json.dump({"username":os.environ["ADMIN_USERNAME"],"password":os.environ["ADMIN_PASSWORD"]},sys.stdout)' > "$TEMP_DIR/credentials.json"
  export -n ADMIN_PASSWORD
  docker run --rm -i --pull never --network none --entrypoint python -v "$SCRIPT_DIR/bootstrap-admin.py:/tmp/bootstrap-admin.py:ro,Z" "heli-monitor-backend:$IMAGE_TAG" /tmp/bootstrap-admin.py validate < "$TEMP_DIR/credentials.json"
  mkdir -p "$INSTALL_DIR" "$DATA_DIR/postgres" "$DATA_DIR/redis" "$DATA_DIR/backups"
  tar -xzf "$CODE_ARCHIVE" -C "$INSTALL_DIR"
  "$PYTHON" "$SCRIPT_DIR/write-env.py" "$INSTALL_DIR/.env" "$DATA_DIR" "$NGINX_PORT" "$IMAGE_TAG"
  cp "$SCRIPT_DIR/manage.sh" "$INSTALL_DIR/manage.sh"; chmod 700 "$INSTALL_DIR/manage.sh"
  cd "$INSTALL_DIR"
  COMPOSE=(docker compose --project-name "$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' .env)" -f docker-compose.offline.yml --env-file .env)
  "${COMPOSE[@]}" config --quiet
  step 5 '启动持久化 PostgreSQL 与 Redis'
  "${COMPOSE[@]}" up -d --pull never postgres redis
  wait_service postgres 80; wait_service redis 80
  step 6 '执行数据库迁移和静态资源准备'
  "${COMPOSE[@]}" run --rm -T --no-deps backend python manage.py migrate --noinput --verbosity 1
  "${COMPOSE[@]}" run --rm -T --no-deps backend python manage.py collectstatic --noinput --verbosity 1
  step 7 '创建应用登录管理员'
  "${COMPOSE[@]}" run --rm -T --no-deps -v "$SCRIPT_DIR/bootstrap-admin.py:/tmp/bootstrap-admin.py:ro,Z" backend python /tmp/bootstrap-admin.py create < "$TEMP_DIR/credentials.json"
  rm -f "$TEMP_DIR/credentials.json"
  step 8 '启动后端与调度服务'
  "${COMPOSE[@]}" up -d --pull never backend worker beat
  wait_service backend 120
  step 9 '启动前端与访问网关'
  "${COMPOSE[@]}" up -d --pull never frontend nginx
  wait_service frontend 80; wait_service nginx 80
  step 10 '核验系统就绪与输出安装结果'
  curl --fail --silent --show-error --retry 10 --retry-all-errors --retry-delay 2 "http://127.0.0.1:$NGINX_PORT/health/ready"
  printf '\n'; "${COMPOSE[@]}" ps
  local ip docker_root
  ip="${SERVER_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"; ip="${ip:-127.0.0.1}"
  docker_root="$(docker info --format '{{.DockerRootDir}}')"
  printf '\n安装完成：Heli Monitor %s\n访问地址：http://%s:%s/\n登录用户：%s\n登录密码：安装时输入的密码（不写入日志）\n数据目录：%s\nPostgreSQL：%s/postgres\nRedis：%s/redis\n应用目录：%s\nDocker 数据目录：%s\n安装日志：%s\n管理命令：%s/manage.sh status\n' "$IMAGE_TAG" "$ip" "$NGINX_PORT" "$ADMIN_USERNAME" "$DATA_DIR" "$DATA_DIR" "$DATA_DIR" "$INSTALL_DIR" "$docker_root" "$LOG_FILE" "$INSTALL_DIR"
  if (( INTERACTIVE )); then printf '\n登录密码（仅本终端显示，不写入日志）：%s\n' "$ADMIN_PASSWORD" > /dev/tty; fi
}
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
