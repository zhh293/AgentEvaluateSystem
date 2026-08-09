# AgentEvaluateSystem

企业级 Agent 评估平台。提交你的 Agent 源码，获取四维评测报告：结果正确性、执行过程质量、效率成本、安全鲁棒性。

## 核心理念

> 评测体系的核心不是堆指标，而是搭桥 —— 从模型能力指标逐层翻译到业务结果指标。

**四层评测覆盖**：结果层 / 过程层 / 效率层 / 风险层，不可只看最终输出。评测的目的是定位行为缺陷并指导迭代，而不只是打分。

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- PostgreSQL 16, Redis 7, RabbitMQ (开发环境由 Docker Compose 提供)

### 本地开发

```bash
# 1. 克隆仓库
git clone https://github.com/zhh293/AgentEvaluateSystem.git
cd AgentEvaluateSystem

# 2. 启动基础设施
cd deploy/docker-compose
docker compose up -d

# 3. 启动后端
cd ../../backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 4. 启动 Celery Worker (新终端)
cd backend
source .venv/bin/activate
celery -A app.core.celery_app worker -Q evaluation --concurrency=4

# 5. 启动前端 (新终端)
cd frontend
npm install
npm run dev
```

访问 `http://localhost:3000` 即可使用。

### 提交 Agent 进行评估

```bash
# 准备你的 Agent 包（示例结构）
my-agent/
├── agent.py              # Agent 主入口
├── requirements.txt      # 依赖声明（可选，会进行漏洞审计）
└── tools/                # 自定义工具（可选）

# 打包并提交
tar -czf my-agent.tar.gz my-agent/
# 先通过 /v1/auth/register 和 /v1/auth/login 获取 API_TOKEN。
# config.json 包含 agent_name、description、llm_provider、llm_model、
# llm_api_base、llm_api_key、enabled_tools 等表单字段。
curl -X POST http://localhost:8000/v1/submissions \
  -H "Authorization: Bearer $API_TOKEN" \
  -F "package=@my-agent.tar.gz" \
  -F "config_data=<config.json"
```

API 接收表单配置并自动生成 `agent.config.yaml`，无需把密钥写入源码包；API Key 仅通过加密、限时、一次性凭据通道交给 Worker。

## Agent 配置模型

系统内部生成的配置结构如下：

```yaml
agent:
  name: "MyAgent"
  version: "1.0.0"
  type: conversational    # conversational | coding | rag | gui | workflow | custom
  description: "简短描述 Agent 的用途"

  llm:
    provider: openai
    model: gpt-4o

  tools:
    - name: search_knowledge_base
      description: "检索知识库"
      risk_level: low

  expected_input:
    type: text
  expected_output:
    type: text

  constraints:
    max_steps: 20
    max_execution_time_seconds: 300
```

## 评测维度

| 维度 | 权重 | 核心指标 |
|------|------|---------|
| **结果层** | 短程 40% / 长程 30% | 准确性、完整性、相关性、连贯性 |
| **过程层** | 短程 20% / 长程 30% | 工具选择准确率、推理路径质量、错误恢复率、幻觉率 |
| **效率层** | 20% | Token 消耗、延迟、步骤效率、任务成本 |
| **风险层** | 20% | Prompt 注入抵抗、越狱抵抗、危险操作拦截率 |

## 报告样例

```json
{
  "overall_score": 78.5,
  "grade": "B+",
  "dimensions": {
    "result": { "score": 82.0, "weight": 0.35 },
    "trajectory": { "score": 75.0, "weight": 0.25 },
    "efficiency": { "score": 72.0, "weight": 0.20 },
    "security": { "score": 85.0, "weight": 0.20 }
  },
  "improvement_suggestions": [
    {
      "severity": "high",
      "dimension": "trajectory",
      "finding": "Agent 在处理模糊查询时频繁调用冗余工具",
      "evidence": "20 个测试用例中，15 个出现了超过 1 次的冗余工具调用",
      "suggestion": "在 System Prompt 中增加工具选择决策树，要求先判断必要性再调用"
    }
  ]
}
```

## 项目结构

```
AgentEvaluateSystem/
├── docs/SDD.md                # 软件设计文档
├── backend/                   # FastAPI + Celery 后端
│   ├── app/
│   │   ├── api/v1/            # REST API 路由
│   │   ├── engine/            # 评测引擎（核心）
│   │   ├── services/          # 业务服务层
│   │   ├── models/            # ORM 模型
│   │   └── worker/            # Celery 异步任务
│   └── tests/
├── frontend/                  # React + TypeScript 前端
│   └── src/
│       ├── pages/             # 页面组件
│       └── components/        # 可复用组件 (RadarChart, TraceViewer)
├── sandbox/                   # 沙箱镜像与运行环境
├── deploy/                    # 部署配置 (K8s / Docker Compose)
└── .github/workflows/         # CI/CD
```

## 技术栈

| 层次 | 技术 |
|------|------|
| 前端 | React 18, TypeScript, Tailwind CSS, ECharts |
| 后端 | Python 3.12, FastAPI, Celery, RabbitMQ |
| 数据 | PostgreSQL 16, Redis 7, MinIO |
| 可观测性 | OpenTelemetry, Jaeger, Prometheus, Grafana |
| 沙箱 | Docker/Docker-in-Docker、只读根文件系统、无网络默认策略、cgroup 资源限制 |
| 部署 | Kubernetes, Docker Compose |

## 安全

所有第三方 Agent 代码在隔离 Docker 沙箱中执行，默认禁网、丢弃 Linux capabilities、启用 no-new-privileges、限制 CPU/内存/PID，并在超时后强制销毁。Kubernetes 通过隔离节点上的 Docker-in-Docker daemon 承载沙箱；如生产威胁模型要求 gVisor 或 Firecracker，需在集群运行时层另行配置，仓库不会虚假宣称已启用。详见 [SDD 第 8 章](docs/SDD.md#8-安全设计)。

## License

MIT
