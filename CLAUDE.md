# CLAUDE.md

## 项目概述

AgentEvaluateSystem 是一个企业级 Agent 评估平台。用户提交 Agent 源代码后，系统在隔离沙箱中自动执行企业级多维度评测，输出评分、雷达图报告、归因分析和改进建议。

**核心设计文档**：`docs/SDD.md`（v2.0 完整版，基于知识库 Agent 评测方法论）

## 关键技术决策

- **后端**: Python 3.12 + FastAPI + Celery + RabbitMQ
- **前端**: React 18 + TypeScript + Tailwind CSS + ECharts
- **沙箱**: 三级隔离 — Docker (只读) / gVisor (可写) / Firecracker VM (高风险)
- **数据**: PostgreSQL 16 / Redis 7 / MinIO
- **可观测性**: OpenTelemetry + Jaeger + Prometheus + Grafana
- **部署**: Kubernetes (生产) / Docker Compose (开发)

## 核心架构（六层模型）

1. 展示层 — React SPA / REST API / WebSocket
2. API 网关层 — 认证鉴权、限流熔断、审计日志
3. 评测编排层 — 任务调度、Pipeline DAG、状态机、门禁、回归触发
4. 评测引擎层 — 短程/长程分流、Skill 评测、AI Judge、对抗评测、评分聚合、归因分析
5. 评测基建层 — 全链路回放、Case 管理、回归引擎、自评修正闭环
6. 沙箱运行时层 — 三级隔离 (只读/可写/高风险)

## 评测体系（核心，详见 `docs/SDD.md` 第 2 章）

- **短程 vs 长程 Agent**：评测策略根本不同。短程=批改作文（6 项指标），长程=审计流水线（Task 三元组）
- **四层评测**: 结果 / 过程 / 效率 / 风险
- **分层指标桥接**: 业务→任务→Agent→模型，层层可追溯（SDD §2.4）
- **客观 + 主观并行**: 能用规则的用规则，剩下的用 LLM-as-Judge 并努力收敛（SDD §2.5）
- **人人一致 + 人机一致**: Dictator 仲裁 + 85% 信任阈值（SDD §2.6）
- **Rubric 二元化**: 是/否/未知，用 Unknown 反查 Rubric 健康度（SDD §2.7）
- **数据飞轮**: 采集→清洗→评测→质检→归因→优化（SDD §2.8）
- **Bad Case 价值 > 通过样本**: 驱动评测体系持续进化（SDD §2.8.3）
- **Skill 全生命周期**: 编写→发版→上线→监控（SDD §2.13）
- **七项基建能力**: 回放/Case/沙箱/AI Judge/归因/回归/门禁（SDD §2.14）
- **自评修正闭环**: 执行→评测→归因→修正→重试，防退化刚性保障（SDD §2.15）
- **五类归因**: 规划/工具调用/Skill/环境/模型能力（SDD §6.4.2）

## 评测引擎模块 (`backend/app/engine/`)

| 文件 | 职责 |
|------|------|
| `result_eval.py` | 结果层评测：短程 6 指标 (准确性/相关性/流畅性/有帮助性/安全性/连贯性)；长程完成率+正确性 |
| `trajectory_eval.py` | 过程层评测：规划质量/工具选择/参数正确性/错误恢复率/幻觉率/步骤冗余 |
| `efficiency_eval.py` | 效率层评测：步骤效率/Token效率/延迟P50-P99/单任务成本 |
| `security_eval.py` | 风险层评测：注入抵抗/越狱抵抗/危险操作拦截/误拒率/数据泄露 |
| `skill_eval.py` | Skill 评测：单 Skill 独立评测 + Skill N+1 集成评测 |
| `llm_judge.py` | AI Judge：双模型独立打分 + 仲裁机制 + 人机一致率持续监控 |
| `adversarial.py` | 对抗评测：PAIR/TAP 自动红队攻击生成 |
| `attribution.py` | 归因分析：五类归因 + 修正策略映射 |
| `aggregator.py` | 评分聚合：加权计算 + Benchmark 对比 |
| `self_eval_loop.py` | 自评修正闭环：防退化重检 + 降级策略 |

## 沙箱安全

沙箱安全设计见 `docs/SDD.md#8-安全设计`。关键原则：

- Agent 风险等级决定隔离强度：LOW→Docker，MEDIUM→Docker+gVisor，HIGH→Firecracker VM
- 所有 Agent 代码提交前需通过静态安全扫描（Bandit + Safety）
- 沙箱网络默认隔离，仅允许 `agent.config.yaml` 中声明的白名单域名
- 沙箱销毁后清理所有临时数据
- 禁止权限提升、严格 seccomp/apparmor 限制

## 常用命令

### 开发环境

```bash
# 后端
cd backend && uvicorn app.main:app --reload --port 8000

# Celery Worker
cd backend && celery -A app.core.celery_app worker -Q evaluation -c 4

# 前端
cd frontend && npm run dev

# 数据库迁移
cd backend && alembic upgrade head

# 运行测试
cd backend && pytest tests/ -v
```

### Docker Compose 完整环境

```bash
cd deploy/docker-compose && docker compose up -d
```

## 文件组织约定

- `docs/` — 设计文档
- `backend/app/api/` — API 路由层（薄层，不含业务逻辑）
- `backend/app/services/` — 业务逻辑层（submission_service, config_generator, model_connectivity, agent_type_identifier, security_service, risk_analyzer, api_key_vault）
- `backend/app/engine/` — 评测引擎（核心评测逻辑，无副作用；含 builtin_tools 系统内置工具库）
- `backend/app/infrastructure/` — 基础设施层（database session, minio client）
- `backend/app/models/` — SQLAlchemy ORM 模型
- `backend/app/schemas/` — Pydantic 请求/响应模型
- `backend/app/worker/` — Celery 异步任务
- `frontend/src/pages/` — 页面级组件
- `frontend/src/components/` — 可复用组件
- `sandbox/` — 沙箱镜像与 Agent Runner

## 编码规范

- 后端使用 Python 3.12+，类型注解必须覆盖所有公共函数
- 前端使用 TypeScript strict 模式
- API 遵循 RESTful 规范，版本化 URL (`/v1/...`)
- 所有评测引擎函数为纯函数，输入数据 → 输出结果，不依赖外部状态
- 沙箱操作必须带超时控制，默认 300 秒，硬超时强制终止
- 日志使用结构化 JSON 格式（对接 ELK/Loki）

## 开发进度

**开发文档**：`docs/DEVELOPMENT.md`（按 Session 推进）

| Session | 状态 | 产出 |
|---------|------|------|
| 0.1 项目脚手架 | ✅ | backend/ (FastAPI), frontend/ (Vite+React+TS+Tailwind), sandbox/, deploy/ |
| 0.2 配置系统与目录规范 | ✅ | config.py, logging.py, exceptions.py, error_handlers.py, .env.example |
| 0.3 前后端联调验证 | ⏭️ 跳过 | — |
| 1.1 Docker Compose 开发环境 | ✅ | docker-compose.yml (5 服务), .env.dev |
| 1.2 数据库模型 & Alembic | ✅ | 9 张表 ORM 模型, Alembic 迁移初始化 |
| 1.3 Pydantic Schema 定义 | ✅ | request/response/internal 三层 15 个 Schema 文件 |
| 2.1 源码包上传 + 配置接收 | ✅ | SubmissionConfigRequest, Submission API, MinIO adapter, API Key Vault, database session |
| 2.2 系统自动生成 agent.config.yaml | ✅ | ConfigGenerator, BuiltinTool 库 (7 tools), YAML 自动生成并上传 MinIO |
| 2.3 模型连通性校验 + AI 类型识别 | ✅ | ModelConnectivityChecker, AgentTypeIdentifier, 连通性前置校验 + 类型自动识别 |
| 2.4 静态安全扫描 + 依赖审计 | ✅ | SecurityScanner (Bandit风格18种危险模式+14个CVE库), 三级处理策略 |
| 2.5 风险定级 + 接入层 API 收尾 | ✅ | RiskAnalyzer, SubmissionService 流水线编排, GET status 接口, 完整接入链路串联 |
| 3.1 沙箱运行时环境 | ⬜ 下一步 | — |
