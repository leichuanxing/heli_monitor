# Heli Monitor v1.0.3 离线部署包

目标平台：**EL9 x86_64（Rocky Linux 9、AlmaLinux 9、RHEL 9）**。包内包含对应 Docker CE、CLI、containerd、Buildx、Compose 及依赖 RPM、v1.0.3 应用镜像和源码，安装不需要访问互联网。其他发行版或 ARM64 请使用匹配的软件包，不要混装本包 RPM。

## 快速安装

```bash
sha256sum -c heli-monitor-offline-v1.0.3-el9-x86_64.tar.gz.sha256
tar -xzf heli-monitor-offline-v1.0.3-el9-x86_64.tar.gz
cd offline
sudo bash install.sh
```

需要 root 权限、systemd、可用磁盘及系统基础工具（Bash、tar、gzip、OpenSSL、curl、Python 3、dnf）。Docker 安装分支适用于 EL9 x86_64。建议至少 4 核、8 GB 内存，并按历史数据量预留空间。

## 交互引导顺序

1. 首先检测 Docker。未安装时询问 Docker 存储目录，默认 **`/var/lib/docker`**；已有 Docker 保留原存储目录和 daemon.json，缺少 Compose 时仅补齐插件。
2. 输入数据持久化目录，默认 **`/opt/monitor`**。
3. 输入应用端口，默认 **`80`**；安装前检查是否被占用。
4. 输入应用登录用户名，默认 **`admin`**。
5. 输入并确认登录密码，至少 12 位，符合应用的相似性、常见密码和纯数字校验。
6. 确认配置，随后显示 10 阶段安装进度、镜像导入、数据库迁移、服务启动和健康检查日志。
7. 安装完成显示访问地址、登录用户、数据目录、Docker 数据目录、日志路径和管理命令。交互终端单独显示登录密码，密码不写入安装日志、环境配置或包内文件。

为保护现有数据，安装器拒绝覆盖已有 `.env` 或 PostgreSQL 数据目录，也不会重置已有账号或自动迁移旧 Docker 数据。请选择新的空目录；已有安装的升级需先备份后单独规划。

## 持久化结构

```text
/opt/monitor/                     # 可在向导中更改
├── app/                         # 源码、编排、0600 权限的 .env 与 manage.sh
├── postgres/                    # PostgreSQL 持久化数据
├── redis/                       # Redis AOF 与持久化数据
├── backups/                     # 手动数据库备份
└── logs/                        # 安装日志，权限 0600
```

每个数据目录使用独立 Compose 项目名，避免与其他应用或在线部署共用容器和数据库。应用镜像固定为 `v1.0.3`，服务使用 `pull_policy: never`，启动使用 `up --pull never`，禁止自动拉取镜像。SELinux 系统使用专用目录的 `:Z` 标记；不要把系统目录或其他应用目录用作安装数据目录。

安装器不会自动修改防火墙或安全组。如需从其他机器访问，请按实际策略放行所选 TCP 端口。使用反向代理或其他域名时相应调整 `app/.env` 中的 `ALLOWED_HOSTS` 和 `CSRF_TRUSTED_ORIGINS` 后重建容器。

## 运维

```bash
/opt/monitor/app/manage.sh status
/opt/monitor/app/manage.sh health
/opt/monitor/app/manage.sh logs backend
/opt/monitor/app/manage.sh stop
/opt/monitor/app/manage.sh start
/opt/monitor/app/manage.sh backup
```

自定义目录请替换路径。`stop` 保留数据；不要删除 postgres、redis、`.env` 或加密密钥。非交互安装须明确提供 `ADMIN_USERNAME`、`ADMIN_PASSWORD`，可同时指定 `DATA_DIR`、`NGINX_PORT`、`DOCKER_DATA_ROOT`；通过受保护的环境或 Secret 注入密码，不要写在命令历史中。非交互安装完成不会输出密码。

安装失败后查看 `logs/install-*.log` 和容器日志。为避免重复初始化，已有环境不会被二次向导自动覆盖。离线安装完整性清单位于 `checksums.sha256`，镜像版本与 ID 见 `images/manifest.txt`。

## 重新打包与验证

先准备 `offline/images/heli-monitor-images.tar.gz` 和 `offline/docker/docker-ce-el9-x86_64-rpms.tar.gz`，再运行：

```bash
bash offline/build-package.sh
python3 -m unittest discover -s offline/tests -v
```

打包排除生产 `.env`、数据库、node_modules、构建缓存和备份，不会将已有业务数据放入离线包。本包不自动上传 GitHub。
