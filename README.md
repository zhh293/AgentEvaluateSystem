# AgentEvaluateSystem

面向 AI Agent 的全链路评测平台。系统接收 Agent 源码包，在隔离沙箱中执行任务，采集结构化 Trace，并从结果、过程、效率和安全四个维度生成可追溯的评测报告。

> 评测不只是给出一个分数，更重要的是解释 Agent 为什么失败、失败发生在哪一步，以及下一轮应该改什么。

## 能力概览

- **安全接入**：ZIP/TAR.GZ 校验、防路径穿越、静态代码扫描、真实依赖漏洞审计、模型端点连通性检查。
- **隔离执行**：按风险等级选择沙箱镜像，默认禁网、只读根文件系统、丢弃 capabilities，并限制 CPU、内存、PID 和执行时间。
- **四维评测**：结果正确性、轨迹质量、Token/延迟/成本、安全与数据泄露风险。
- **Rubric 系统**：内置 Rubric、配置推导、场景模板、AI 生成、Case 解析和健康度监控。
- **AI Judge**：严格 JSON 输出、真实 Span 证据校验、双 Judge、仲裁和人工复核标记。
- **专项能力**：Skill 单测与组合测试、100 条静态对抗 Case、PAIR/TAP、回归分析、质量门禁和自评修正闭环。
- **可观测与回放**：OpenTelemetry Trace、SSE 回放、WebSocket 进度、Prometheus 指标、Grafana Dashboard 和告警。
- **生产工程**：JWT/RBAC、资源所有权隔离、Redis 限流、熔断、审计日志、Docker Compose、Kubernetes 和 GitHub Actions。

## 系统架构

```text
React Web
   │  REST / WebSocket / SSE
   ▼
FastAPI Gateway ───── PostgreSQL
   │                  Evaluation / Case / Audit metadata
   ├───────────────► MinIO
   │                  source packages / configs / traces
   ▼
RabbitMQ → Celery Worker → Docker Sandbox
                           │
                           ├─ Agent execution
                           ├─ OTel trace capture
                           └─ four-dimensional evaluators
                                      │
                                      ▼
                             aggregation / attribution / report

Redis: Celery result backend、限流、一次性加密凭据、跨进程进度事件
Jaeger / Prometheus / Grafana: tracing、metrics、dashboard、alerts
```

完整设计与分阶段实现说明：

- [软件设计文档](docs/SDD.md)
- [开发任务文档](docs/DEVELOPMENT.md)

## 技术栈

| 层次 | 技术 |
| --- | --- |
| Web | React、TypeScript、Vite、ECharts、Vitest |
| API | FastAPI、Pydantic、SQLAlchemy、Alembic |
| 异步任务 | Celery、RabbitMQ、Redis |
| 数据与对象存储 | PostgreSQL、MinIO |
| 沙箱 | Docker SDK、独立风险镜像、Docker-in-Docker（K8s） |
| 评测 | 规则引擎、Rubric、双 LLM Judge、PAIR/TAP |
| 可观测性 | OpenTelemetry、Jaeger、Prometheus、Grafana |
| 交付 | Docker Compose、Kubernetes、GitHub Actions |

## 快速开始

### 环境要求

- Python 3.11+（生产镜像使用 Python 3.12）
- Node.js 22+
- Docker Engine 或 Docker Desktop
- Docker Compose v2

Windows PowerShell 与 Linux/macOS 命令分别在下面标注。

### 1. 克隆项目

```bash
git clone https://github.com/zhh293/AgentEvaluateSystem.git
cd AgentEvaluateSystem
```

### 2. 构建沙箱镜像

Windows PowerShell：

```powershell
.\sandbox\build.ps1
```

Linux/macOS：

```bash
./sandbox/build.sh
```

将生成：

- `agenteval/sandbox:readonly`
- `agenteval/sandbox:writable`
- `agenteval/sandbox:highrisk`

### 3. 启动基础设施

```bash
cd deploy/docker-compose
docker compose --env-file .env.dev up -d postgres redis rabbitmq minio jaeger prometheus grafana
cd ../..
```

本地端口：PostgreSQL `5432`、Redis `6379`、RabbitMQ `5672/15672`、MinIO `9000/9001`、Jaeger `16686`、Prometheus `9090`、Grafana `3001`。

`.env.dev` 只包含本地开发凭据，不应复用于生产环境。

### 4. 启动后端

Windows PowerShell：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Linux/macOS：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

健康检查与接口文档：

- `http://localhost:8000/health`
- `http://localhost:8000/docs`
- `http://localhost:8000/metrics`

### 5. 启动 Worker

新终端进入 `backend` 并激活同一虚拟环境：

```bash
celery -A app.core.celery_app worker -Q evaluation --concurrency=4
```

Worker 需要访问本机 Docker daemon。Windows Docker Desktop 使用其默认 Docker context；Linux 用户需确保当前用户有权访问 `/var/run/docker.sock`。

### 6. 启动前端

```bash
cd frontend
npm ci
npm run dev
```

访问 `http://localhost:3000`，注册账号后即可提交 Agent。

## Agent 包约定

支持 `.zip`、`.tar.gz` 和 `.tgz`，解压后必须包含 `agent.py`。入口可以采用以下任一形式：

```python
def run(task: dict): ...
def run_agent(task: dict): ...
def main(task: dict): ...

class Agent:
    def run(self, task: dict): ...
```

入口可以返回字符串、字典或其他可 JSON 序列化的数据，也可以是异步函数。

推荐目录：

```text
my-agent/
├── agent.py
├── requirements.txt       # 可选；提交时进行依赖漏洞审计
└── tools/                 # 可选
```

不要把模型密钥写入源码包。提交 API 会接收密钥，通过 Redis 加密保存 15 分钟，并在 Worker 首次读取后立即销毁。

## API 使用示例

### 1. 注册与登录

```bash
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","email":"demo@example.com","password":"change-me-123"}'

curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"change-me-123"}'
```

将返回的 `access_token` 保存为 `API_TOKEN`。

### 2. 准备提交配置

```json
{
  "agent_name": "Research Agent",
  "version": "1.0.0",
  "description": "检索指定知识源并生成带引用的结构化研究结论，能够处理检索失败与空结果。",
  "llm_provider": "openai",
  "llm_model": "your-model",
  "llm_api_base": "https://your-endpoint.example/v1",
  "llm_api_key": "runtime-only-key",
  "subtype": "rag",
  "enabled_tools": ["knowledge_base_search"],
  "language": "简体中文",
  "max_steps": 20,
  "max_execution_time_seconds": 300,
  "allowed_domains": ["your-endpoint.example"]
}
```

描述至少 30 个字符。`agent_type` 和 `subtype` 可以留空，由系统识别；生产环境建议明确声明并人工复核。

### 3. 提交并启动评测

```bash
curl -X POST http://localhost:8000/v1/submissions \
  -H "Authorization: Bearer $API_TOKEN" \
  -F "package=@my-agent.tar.gz" \
  -F "config_data=<config.json"

curl -X POST http://localhost:8000/v1/evaluations/SUBMISSION_ID/start \
  -H "Authorization: Bearer $API_TOKEN"
```

### 4. 查询结果与 Trace

```bash
curl http://localhost:8000/v1/evaluations/EVALUATION_ID/report \
  -H "Authorization: Bearer $API_TOKEN"

curl http://localhost:8000/v1/evaluations/EVALUATION_ID/trace \
  -H "Authorization: Bearer $API_TOKEN"

curl -N http://localhost:8000/v1/evaluations/EVALUATION_ID/trace/replay \
  -H "Authorization: Bearer $API_TOKEN"
```

WebSocket 进度地址：

```text
ws://localhost:8000/v1/ws/SUBMISSION_ID?token=API_TOKEN
```

## 评分体系

| 维度 | 短程 Agent | 长程 Agent | 典型指标 |
| --- | ---: | ---: | --- |
| 结果 | 40% | 30% | 准确性、任务成功率、正确性、安全输出 |
| 过程 | 20% | 30% | 工具选择、参数正确性、计划质量、恢复率、冗余与幻觉 |
| 效率 | 20% | 20% | 步骤、Token、P50/P90/P99 延迟、单任务成本 |
| 安全 | 20% | 20% | 注入/越狱、危险操作阻断、过度拒绝、数据泄露 |

无法可靠程序化判断的项目会标记为 `pending_llm`、`Unknown` 或 `needs_review`，不会伪造确定分数，也不会把未知项当作失败项直接计入分母。

## Case、回归与门禁

系统维护核心、扩展、对抗和回归四层 Case：

- `GET /v1/test-cases`：浏览与筛选 Case。
- `POST /v1/test-cases`：创建 Draft Case（管理员）。
- `POST /v1/test-cases/convert`：将失败评测转为回归 Case。
- `PUT /v1/test-cases/{id}/publish`：发布 Case。
- `PUT /v1/test-cases/{id}/archive`：归档 Case。
- `GET /v1/quality-gates/{submission_id}`：查询门禁记录。
- `POST /v1/quality-gates/{submission_id}/check`：执行并保存门禁检查。

仓库内置 100 条、5 类静态对抗用例，并提供 PAIR/TAP 有界攻击生成器。

## 测试与安全审计

后端：

```bash
cd backend
python -m pytest tests -q
bandit -r app -q -lll -x app/data
pip-audit -r requirements.txt --progress-spinner off
```

前端：

```bash
cd frontend
npm test
npm run build
npm audit
```

Kubernetes 离线 Schema 校验：

```bash
python -m pip install kubernetes-validate
python -m kubernetes_validate --strict deploy/kubernetes/*.yaml
```

当前仓库基线：后端 72 项测试、前端 3 项测试；Python 与 npm 依赖审计均无已知漏洞。

## Docker Compose

启动完整应用栈：

```bash
cd deploy/docker-compose
docker compose --env-file .env.dev up -d postgres redis rabbitmq minio
docker compose --env-file .env.dev run --rm backend alembic upgrade head
docker compose --env-file .env.dev up --build -d
```

生产环境不要使用 `.env.dev` 中的默认密码。

## Kubernetes 部署

1. 根据 [`deploy/kubernetes/examples/secret.example.yaml`](deploy/kubernetes/examples/secret.example.yaml)通过 External Secrets、Sealed Secrets 或云密钥服务创建 `agent-eval-secrets`。
2. 替换镜像仓库、Ingress 域名、TLS Secret 和存储类。
3. 给沙箱节点设置标签和污点：

```bash
kubectl label node SANDBOX_NODE workload=agent-sandbox
kubectl taint node SANDBOX_NODE workload=agent-sandbox:NoSchedule
```

4. 应用清单：

```bash
kubectl apply -f deploy/kubernetes/
```

清单包括 API/Worker/Frontend、PostgreSQL、Redis、RabbitMQ、MinIO、Jaeger、Prometheus、Grafana、HPA、Ingress、持久卷、NetworkPolicy 和独立沙箱 daemon。

## 安全边界

- 上传包限制类型、压缩前后大小，并拒绝路径穿越、符号链接和特殊文件。
- API Key 不进入数据库、日志、Trace 或报告；凭据加密、限时且一次性读取。
- 非管理员只能访问自己的 Submission、Evaluation 和 Trace；管理接口使用 RBAC。
- 沙箱默认 `network=none`、`cap_drop=ALL`、`no-new-privileges`、cgroup 限额和强制超时销毁。
- K8s sandbox daemon 只允许 Worker 通过 NetworkPolicy 访问。
- 审计中间件记录用户、路径、状态码、耗时、IP 和 User-Agent，不记录请求正文或密钥。

当前仓库提供 Docker 级隔离和按风险划分的镜像。gVisor、Kata Containers 或 Firecracker 属于集群运行时能力，需要依据生产威胁模型在基础设施层额外配置；项目不会把未启用的运行时声明为已启用。

## 项目结构

```text
AgentEvaluateSystem/
├── backend/
│   ├── app/api/v1/             # REST、SSE、WebSocket API
│   ├── app/engine/             # Rubric 与评测引擎
│   ├── app/infrastructure/     # MinIO、Case、回归、门禁、回放
│   ├── app/services/           # 接入、沙箱、Trace、报告、编排服务
│   ├── app/worker/             # Celery Canvas DAG
│   ├── migrations/             # Alembic 数据库迁移
│   └── tests/                  # 后端测试
├── frontend/                   # React 控制台及前端测试
├── sandbox/                    # Agent runner、OTel 与三类沙箱镜像
├── deploy/
│   ├── docker-compose/
│   ├── kubernetes/
│   ├── prometheus/
│   └── grafana/
├── docs/SDD.md
├── docs/DEVELOPMENT.md
└── .github/workflows/         # CI/CD
```

## 运维入口

| 服务 | 默认地址 |
| --- | --- |
| Web | `http://localhost:3000` |
| API / Swagger | `http://localhost:8000` / `http://localhost:8000/docs` |
| RabbitMQ Management | `http://localhost:15672` |
| MinIO Console | `http://localhost:9001` |
| Jaeger | `http://localhost:16686` |
| Prometheus | `http://localhost:9090` |
| Grafana | `http://localhost:3001` |

## License

MIT
