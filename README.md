# Heli Monitor · 合力数据业务监控系统

**版本：v1.0.3 · 发布日期：2026-10-30**

面向业务可用性的监控与运维管理平台。通过网络、接口和数据库探测采集实际结果，集中展示业务状态、响应趋势、故障事件及 SLA，并按规则投递告警通知。

## v1.0.3 更新

- 新增监控大屏选择页，提供“经典运维大屏”和“全景驾驶舱”两套布局。
- 两套大屏均支持一屏展示、浏览器全屏及随窗口变化自动调整；适配 1080P、2K、4K、超宽屏和 16:10 等比例。长清单支持手动翻页、自动轮播；不通过截断列表隐藏任务。
- 大屏使用独立深色主题，提供可关闭的轻量动效；响应趋势默认查询最近 12 小时，可切换周期，使用逐次原始数据和平滑曲线。
- 统一管理平台的导航、品牌、表单、表格、弹窗、图表与浅色/深色主题，完善状态页及移动端交互。
- 探测任务编辑采用紧凑双列布局，按协议展示参数，折叠高级连接选项和告警策略；新增任务提供周期、超时建议，编辑时保留已有配置。
- 简化 HTTP/API 请求体、认证与响应校验配置。支持 Bearer、Basic、API Key、OAuth2 客户端凭据；已移除“登录获取 Token”认证选项。
- SSL 探测记录证书到期时间和有效期天数，支持到期前预警及关联规则通知。任务历史弹窗顶部保留证书有效期卡片；汇总历史趋势页不显示该卡片。
- 同步根目录版本、前端版本显示、后端 OpenAPI 版本及 Git 标签为 v1.0.3。

## 功能范围

| 模块 | 主要功能 |
| --- | --- |
| 监控中心 | 总览、双布局大屏、任务管理、结果明细、历史趋势、业务链路 |
| 探测协议 | HTTP、API、TCP、PING、DNS、SSL、MySQL/MariaDB、PostgreSQL、SQL Server、MongoDB |
| 任务管理 | 新增、编辑、复制、启停、立即探测、批量操作及历史数据弹窗 |
| 资产管理 | 业务系统、分组、标签及关联关系 |
| 事件与告警 | 故障事件确认、处理与关闭；告警规则、持续提醒、恢复通知、投递记录及重试 |
| 通知渠道 | SMTP 邮件、Webhook、企业微信、钉钉、Server 酱 |
| 维护与报表 | 维护窗口、样本口径 SLA、CSV 导出、公开或受令牌保护的状态页 |
| 组织与权限 | 用户、部门、角色及模块功能授权 |
| 系统管理 | 品牌、刷新周期、登录记录、审计日志、系统健康和维护操作 |

历史趋势最长查询 30 天。响应曲线展示实际保留的逐次记录，不按时间桶取平均；统计卡片另行提供平均值、最大值和成功率。无记录的时段不补作成功。历史保留受系统清理策略影响，已清理记录无法恢复。

**删除探测任务会永久删除相关探测历史。** 普通启停和编辑不会删除历史。权限按模块功能控制，目前不提供部门或个人级数据行隔离。通知和认证敏感字段通过现有加密机制保存；不要将生产凭据提交到代码仓库。

详细参数见 [探测任务与历史数据](docs/monitor-options.md)，界面规范见 [前端设计说明](frontend/DESIGN.md)。

## 架构与目录

- 后端：Python 3.12、Django 5、DRF、Channels、Celery。
- 前端：Vue 3、TypeScript、Element Plus、ECharts、Vite。
- 数据与队列：PostgreSQL 16、Redis 7。
- 部署：Docker Compose、Nginx；Web、Worker、Beat 分进程运行。

```text
backend/              API、探测执行、告警、权限、数据库迁移与测试
frontend/             管理界面、监控大屏、组件与前端测试
deploy/nginx/         反向代理配置
scripts/              应用管理及 HTTP 冒烟检查
docs/                 使用说明
offline/              离线安装与打包脚本
VERSION               v1.0.3
docker-compose.yml    在线构建与部署
.env.example          环境配置模板
```

## 安装与部署

准备 Linux、Docker Engine 24+ 和 Docker Compose v2。建议起步配置为 4 核 CPU、8 GB 内存；实际资源和磁盘需求取决于任务数量、探测周期和数据保留量。

```bash
git clone https://github.com/leichuanxing/heli_monitor.git
cd heli_monitor
git checkout v1.0.3
cp .env.example .env
chmod 600 .env
```

部署前编辑 `.env`：

- 设置随机 `DJANGO_SECRET_KEY` 和 `SECRET_ENCRYPTION_KEY`；升级时保留已有加密密钥。
- 设置 `POSTGRES_PASSWORD`，并保持 `DATABASE_URL` 中的凭据一致。
- 配置实际的 `ALLOWED_HOSTS`、`CSRF_TRUSTED_ORIGINS`、`NGINX_PORT` 和时区。
- 按允许的监控网络配置 `ALLOWED_PROBE_CIDRS`、`BLOCKED_PROBE_PORTS`，不要直接放开不需要的网络访问。

仓库不提供固定生产管理员密码，也不包含生产数据库、`.env` 或镜像归档。

```bash
chmod +x scripts/app.sh
./scripts/app.sh start
docker compose exec backend python manage.py createsuperuser
./scripts/app.sh health
```

入口脚本执行数据库迁移和静态资源收集。新用户密码需通过当前密码策略。首次部署可通过浏览器打开服务器地址登录。

| 入口 | 用途 |
| --- | --- |
| `/` | Web 管理平台 |
| `/monitor-wall` | 大屏缩略图选择页 |
| `/monitor-wall/classic` | 经典运维大屏 |
| `/monitor-wall/panorama` | 全景驾驶舱 |
| `/api/v1/docs/` | OpenAPI 文档 |
| `/health/live` | 存活检查 |
| `/health/ready` | 依赖就绪检查 |

## 使用建议

1. 建立业务系统，按需关联分组和标签。
2. 新增任务，填写目标及协议参数；先执行一次立即探测核对结果。
3. 配置通知渠道和告警规则，在授权的接收端验证故障与恢复投递。
4. 在结果明细或任务历史弹窗查看原始记录；在监控大屏中选择布局，点击“全屏”展示。
5. 通过事件、通知发送记录、维护窗口及 SLA 报表跟踪处理过程。

数据库探测应使用目标系统的专用只读账号。API 的 OAuth2 客户端凭据认证要求对端支持该流程；不提供任意登录接口的通用 Token 获取流程。SSL 通知需要已启用并匹配的告警规则和通知渠道，只有页面预警并不代表已发送通知。

SLA 按实际保留样本计算，不等同于对缺失时段作出的可用性承诺；结合维护窗口、失败明细及保留策略理解结果。大屏的“近期事件”“最近探测”和 TOP 5 是明确限定的窗口；全量任务清单可翻页查看。

## 更新与日常运维

```bash
./scripts/app.sh status
./scripts/app.sh logs backend
./scripts/app.sh health
./scripts/app.sh update
./scripts/app.sh stop
```

`update` 构建当前目录代码，不自动拉取 Git。升级前备份 PostgreSQL、`.env` 和加密密钥，保留可回退的应用镜像及源码。普通停机不要执行 `docker compose down -v`，该命令会删除数据卷。容器重建后如代理仍指向旧容器，可执行：

```bash
docker compose exec nginx nginx -s reload
```

## 开发与验证

前端建议使用 Node.js 22；在 `frontend` 中安装依赖并运行：

```bash
npm install --no-audit --no-fund
npm run lint
npm test
npm run build
```

生产前端容器仅提供静态文件，不包含 Node.js。标准 Dockerfile 的构建阶段会执行检查、测试及构建。

后端测试应使用隔离 PostgreSQL、受控目标和模拟通知接收端。配置测试环境后可运行：

```bash
docker compose run --rm backend ruff check .
docker compose run --rm backend pytest -o addopts='' -q
docker compose run --rm backend python manage.py makemigrations --check --dry-run
docker compose run --rm backend python manage.py spectacular --validate --file /tmp/schema.yml
docker compose exec backend python manage.py check_application
python3 scripts/smoke_test.py http://127.0.0.1
```

不要把“页面可打开”或模拟测试通过视为所有外部探测和通知渠道已经验证；真实目标、网络和接收端须在部署环境逐项核验。

## 离线部署与排障

离线脚本和依赖准备要求见 [offline/README.md](offline/README.md)。打包脚本从 `VERSION` 读取版本，v1.0.3 包名为 `heli-monitor-offline-v1.0.3-el9-x86_64.tar.gz`。Git 标签仅包含源码，不代表已提供对应的离线镜像或完整安装包。

- 页面或接口异常：检查 Nginx、服务健康、端口及访问域名配置。
- 任务不执行：检查业务及任务是否启用、Worker、Beat、Redis 和目标网络策略。
- 告警未收到：核对规则、渠道、事件状态、发送记录及接收端可达性。
- 登录失效：确认令牌和密码是否变更，必要时重新登录。
- 加密配置无法读取：保留并恢复原密钥；更换密钥不能解密旧配置。
