# CLAUDE.md

## 项目概述

AgentEvaluateSystem 是一个企业级 Agent 评估平台。用户提交 Agent 源代码后，系统在隔离沙箱中自动执行四维评测（结果/过程/效率/安全），输出评分、雷达图报告和改进建议。

## 关键技术决策

- **后端**: Python 3.12 + FastAPI + Celery + RabbitMQ，AI/ML 生态成熟，异步高性能
- **前端**: React 18 + TypeScript + Tailwind CSS + ECharts
- **沙箱**: Docker + gVisor (容器级) / Firecracker (VM级强隔离)
- **数据**: PostgreSQL 16（结构化数据）、Redis 7（缓存/队列状态）、MinIO（对象存储）
- **可观测性**: OpenTelemetry + Jaeger + Prometheus + Grafana
- **部署**: Kubernetes（生产）、Docker Compose（开发）
- **CI/CD**: GitHub Actions

## 核心架构（六层模型）

1. 展示层 — React SPA / REST API / WebSocket
2. API 网关层 — 认证鉴权、限流熔断、审计日志
3. 评测编排层 — 任务调度、Pipeline 编排、状态机管理
4. 评测引擎层 — 静态分析、基准测试、LLM-as-Judge、轨迹评测、对抗评测、评分聚合
5. 沙箱运行时层 — Docker/gVisor/Firecracker 隔离执行
6. 基础设施层 — K8s、PostgreSQL、Redis、MinIO

## 评测体系（核心）

评测体系遵循方法论（来自个人知识库 doc:`07-agent`）：

- **四层评测**: 结果层（Response Evaluation）+ 过程层（Trajectory Evaluation）+ 效率层 + 风险层
- **双轨并行**: 客观指标 + LLM-as-Judge 主观评测
- **分层指标桥接**: 业务层 → 任务层 → Agent 层 → 模型层，层层可追溯
- **人机一致性校验**: LLM-as-Judge 与人评一致性需 ≥ 85%
- **Rubric 二元化**: 模糊指标拆为 是/否/未知
- **安全第一**: 所有第三方 Agent 代码默认不信任，沙箱强隔离

评测引擎是系统的核心模块，代码位于 `backend/app/engine/`，包含六个子引擎：

| 文件 | 职责 |
|------|------|
| `result_eval.py` | 结果层评测：准确性、完整性、相关性、连贯性 |
| `trajectory_eval.py` | 过程层评测：工具选择正确率、推理路径质量、幻觉率 |
| `efficiency_eval.py` | 效率层评测：Token 消耗、延迟、步骤效率、成本 |
| `security_eval.py` | 风险层评测：Prompt 注入、越狱、危险操作拦截 |
| `llm_judge.py` | LLM-as-Judge：双 Judge 独立打分，偏差 > 2 分引入第三仲裁 |
| `adversarial.py` | 对抗评测：PAIR/TAP 自动红队攻击生成 |
| `aggregator.py` | 评分聚合：加权计算 + Benchmark 对比 + 归因分析 |

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
- `backend/app/services/` — 业务逻辑层
- `backend/app/engine/` — 评测引擎（核心评测逻辑，无副作用）
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
