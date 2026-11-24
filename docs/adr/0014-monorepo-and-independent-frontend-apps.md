---
status: accepted
date: 2026-11-24
---

# ADR-0014：Monorepo 管理后端与两个独立前端应用

用户已确认整个项目采用 Monorepo，Chat 与 Admin 分成两个独立前端应用，以分别构建、发布和部署，并在同一仓库协同维护公共能力及后端 API。相较单应用内的两个入口，这增加两套应用配置与发布检查，但能分别演进员工对话体验和管理工作台。

前端采用 create-vite 的 React + TypeScript 基础模板，pnpm workspace 管理 `frontend/apps/chat`、`frontend/apps/admin` 及 `frontend/packages/*`；两个应用各自拥有入口、路由、配置、构建产物和部署目标。公共组件、API 客户端/生成类型与工具通过公共包显式导出，应用间不直接导入源码，公共包不依赖应用。

后端使用 uv 管理 Python 依赖，以 FastAPI 工程骨架沿用模块化单体、独立 Worker 及现有 API/业务/Adapter 边界；脚手架负责工程配置，业务模块按版本任务增量实现。详细目录与初始化任务见 [V1.0 代码结构](../plan/V1.0-MVP/05-code-structure-and-backlog.md) 和 [实施计划](../plan/V1.0-MVP/06-完整研发实施计划与阶段验收标准.md)。

版本、锁文件、启动和构建命令在实际源码仓初始化时落地。CI 按受影响的项目执行检查；公共包或后端 API 契约变化必须覆盖相应前端消费者。独立部署继续使用同一后端授权契约，具体域名、登录配置和 API 地址按真实环境配置。

本决策记录已确认的工程组织与基础工具选择，不表示源码、依赖安装或 CI 已完成。产品继续沿用 [ADR-0013](0013-single-enterprise-deployment-scope.md) 的单一企业内部部署范围。
