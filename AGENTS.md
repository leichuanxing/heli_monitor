# AGENTS.md

本仓库开发企业级业务可用性监控系统。所有改动必须可运行、可测试、可部署，不得以静态页面或假数据冒充功能完成。

- 后端：Python 3.12、Django 5、DRF、Celery、Channels。
- 前端：Vue 3、TypeScript、Vite、Element Plus、ECharts。
- 数据：PostgreSQL、Redis。
- 部署：Docker Compose、Nginx、Gunicorn/Uvicorn。
- 密钥仅通过环境变量或 Secret 模型使用；API、日志与测试快照不得泄露密文。
- 模型变更必须包含迁移，API 变化同步更新 OpenAPI 和前端类型。
- 改动后执行单元测试、Lint、类型检查、构建与相关健康检查，并只报告实际执行结果。

