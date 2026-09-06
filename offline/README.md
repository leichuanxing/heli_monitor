# 合力数据业务监控系统离线部署包

本目录用于在无外网 Linux 服务器上部署合力数据业务监控系统，包含应用源码、全部 Docker 镜像、配置模板和安装管理脚本。

## 文件结构

```text
offline/
├── install.sh                         一键安装脚本
├── manage.sh                          启停、状态、日志、备份管理脚本
├── build-package.sh                   重建代码归档、校验文件和完整交付包
├── config/.env.example                配置参考
├── docker/docker-ce-el9-x86_64-rpms.tar.gz
│                                         Docker CE、containerd、Buildx、Compose 及依赖
├── images/heli-monitor-images.tar.gz  全部 Docker 镜像
├── packages/heli-monitor-code.tar.gz  完整应用代码
└── checksums.sha256                   安装包完整性校验
```

## 环境要求

- Rocky Linux 9、AlmaLinux 9、RHEL 9 等 EL9 兼容系统（x86_64）
- 默认端口 80 可用
- 建议至少 4 核 CPU、8 GB 内存、20 GB 可用磁盘

安装脚本首先检查 Docker Engine 和 Docker Compose v2。两者均可用时保留现有安装并直接启动 Docker；任一缺失时，使用包内 RPM 和完整依赖离线安装 Docker CE、containerd、Buildx 与 Compose，不访问外部软件源。

## 安装

```bash
chmod +x install.sh manage.sh
./install.sh
```

安装脚本会启动交互式向导，要求输入：

- 系统管理用户名，默认为 `admin`
- 系统管理密码，隐藏输入并进行二次确认，至少 8 位
- 系统管理员邮箱，可留空
- 业务访问端口，默认为 `80`
- 应用部署目录，默认为 `/opt/heli_monitor`，必须使用绝对路径

确认配置后才会开始安装。也可以使用环境变量进行无人值守安装：

```bash
ADMIN_USERNAME=admin \
ADMIN_PASSWORD='强密码' \
ADMIN_EMAIL=admin@example.com \
NGINX_PORT=8080 \
INSTALL_DIR=/data/heli_monitor \
./install.sh
```

无人值守安装必须设置 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD`。

安装脚本会依次完成系统检查、Docker 检测或离线安装、镜像导入、代码部署、数据库凭据同步、数据库迁移和健康检查。数据库迁移作为独立前台步骤执行，会显示每个 Django 迁移的执行过程。脚本同时自动生成 Django 密钥、数据库密码和数据加密密钥，并将 `.env` 权限设置为 `600`。

重复安装会保留已有 `.env` 和 PostgreSQL 数据卷。安装器会将已有数据库角色密码同步为当前 `.env` 配置，避免更换安装包或重新生成容器后出现 `password authentication failed`。

## 日常管理

```bash
./manage.sh status
./manage.sh health
./manage.sh start
./manage.sh stop
./manage.sh restart
./manage.sh logs backend
./manage.sh create-admin
./manage.sh backup
```

也可以指定安装目录：

```bash
INSTALL_DIR=/data/heli_monitor ./manage.sh status
```

`stop` 不删除 PostgreSQL 和 Redis 数据卷。脚本不提供自动删除数据卷功能。

## 完整性校验

```bash
sha256sum -c checksums.sha256
```

## 更新部署包

重新生成的安装包可覆盖旧的镜像和源码归档。更新生产系统前应先执行：

```bash
./manage.sh backup
```

然后使用新包中的安装脚本部署；已有 `.env` 会被保留。

在联网构建机上完成镜像构建并将所需镜像归档放入 `images/`、Docker RPM 归档放入 `docker/` 后，可重新封装：

```bash
chmod +x build-package.sh
./build-package.sh
```

版本号读取自项目根目录的 `VERSION`。默认生成 `heli-monitor-offline-v1.0.1-el9-x86_64.tar.gz` 及对应的 `.sha256` 校验文件，也可以把目标文件路径作为第一个参数传入。
