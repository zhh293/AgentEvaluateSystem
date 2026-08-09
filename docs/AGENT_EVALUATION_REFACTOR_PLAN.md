# Agent 评估平台架构修复与重构方案

> 文档状态：Draft
> 适用范围：`ModelEvaluateSystem` 下一阶段架构与业务链路重构
> 核心目标：将当前平台重构为以“能力说明书驱动测试、可信拓扑重建、多 Case 隔离执行、四维证据化评估”为主线的 Agent 验收与持续质量平台。

---

## 1. 背景与问题定义

当前项目已经具备提交校验、源码安全扫描、镜像构建、镜像安全扫描、SBOM、沙箱执行、Trace、四维评价、报告和质量门禁等基础模块，但这些模块尚未完整组成目标业务闭环。

本次重构需要建立以下唯一主链路：

```text
提交 Agent 交付物
  → 接入校验
  → 安全与配置分析
  → 隔离异步构建及镜像扫描
  → 生成可信 Manifest
  → 解析功能说明书并建立能力目录
  → 多 Agent 生成并评审 Case + Rubric
  → 根据可信 Manifest 重建沙箱运行拓扑
  → 执行全部 CLI 命令或 API Case
  → 采集 Result、Trace、Tool Call、Token、延迟和成本
  → 结果、过程、效率、安全四维并行评估
  → 汇总评分或标记 needs_review
  → 报告、回放、归因、回归、历史比较和质量门禁
```

平台的基本原则是：

1. 用户上传的说明书中声明的所有公开功能都进入测试范围。
2. 用户 Compose 只用于声明服务拓扑，平台绝不直接执行原始 Compose。
3. 用户不再负责编写平台内部 Manifest，可信 Manifest 由平台校验后生成。
4. 只有构建和镜像扫描完成、状态达到 `image_ready` 的提交才能创建评估任务。
5. 所有分数都必须能够关联到 Case、Rubric、执行结果和 Trace 证据。
6. 证据不足时返回 `unknown` 并将评估标记为 `needs_review`，不强行给分。

---

## 2. 重构目标与非目标

### 2.1 重构目标

- 将提交方式统一为源码、运行配置、功能说明书和 Docker Compose。
- 单服务和多服务统一使用 Compose 描述，不再维护两套部署流程。
- 从运行配置和 Compose 生成平台内部可信 Manifest。
- 支持 OpenAPI 和 CLI 说明书的结构化能力发现。
- 自动生成约 30～60 条与 Agent 功能匹配的 Case + Rubric。
- 引入多 Agent Council 对测试集进行生成、匿名评审、覆盖审计和最终裁决。
- 将当前单任务执行改造成 Evaluation 下的多 Case 扇出执行。
- 完整保存 Case 级 Result、Trace、工具调用、Token、延迟、成本和裁判证据。
- 维持短程与长程 Agent 的差异化四维权重。
- 建立坏例转回归、历史对比和质量门禁闭环。

### 2.2 非目标

- 不直接执行用户提交的 Docker Compose。
- 不允许用户通过 Compose 自行配置特权、宿主网络、设备或 Docker Socket。
- 不允许把 LLM API Key 等秘密写入源码包、Compose、镜像层、构建参数或持久化 Manifest。
- 不追求任意 Compose 语法的完全兼容，只支持平台定义的安全子集。
- 不将所有 Rubric 都交给 LLM 判断；可程序化检查的规则必须优先使用程序化判定。
- 第一阶段不支持任意自然语言说明书的无校验自动执行。

---

## 3. 当前实现与目标方案的主要差距

### 3.1 提交协议不一致

当前源码包要求包含 `agent-eval.yaml`，同时支持 Compose 和 Dockerfile 两种部署模式。目标方案要求用户只提供真实交付物，由平台生成内部运行契约。

需要调整为：

```text
用户交付物                        平台内部产物
────────────────────────────────────────────────
源码包                 ┐
Docker Compose         ├── 校验与规范化 ──→ Verified Manifest
运行配置               ┤
CLI/API 功能说明书     ┘
```

### 3.2 缺少说明书驱动的能力发现

当前平台主要根据 Agent 描述和配置生成 Rubric，没有形成：

```text
说明书功能 → Capability → Case → Rubric → Invocation → Evidence
```

因此无法证明说明书中的全部命令或接口都已覆盖。

### 3.3 当前执行粒度仍然是单任务

当前评估执行服务主要执行一个 `evaluation_task`。目标结构应为一个 Evaluation 包含 30～60 个独立 Case，每个 Case 产生自己的调用、结果、Trace 和 Rubric 判定。

### 3.4 状态机没有覆盖完整生命周期

当前构建状态、提交状态和评估状态存在部分重叠，且评估状态机没有完整表达能力发现、Case 生成和 Council 评审阶段。

### 3.5 Case 生成器规模和职责不足

当前 AI Rubric 生成器每次生成 8～15 条 Rubric，但目标是生成 30～60 个完整 Case，每个 Case 可包含多条二元 Rubric，并需要覆盖审计、去重、可执行性检查和多 Agent 评审。

---

## 4. 目标领域模型

建议将平台核心对象明确为以下层级：

```text
Submission
  ├── SourceArtifact
  ├── ComposeArtifact
  ├── RuntimeConfigArtifact
  ├── InterfaceSpecArtifact
  ├── SecurityAnalysis
  ├── ImageBuild
  │     ├── ServiceImage[]
  │     ├── BuildLog
  │     ├── ImageScanReport
  │     └── SBOM
  ├── VerifiedManifest
  └── CapabilityCatalog

Evaluation
  ├── CaseSetVersion
  ├── EvaluationCase[]
  │     ├── Invocation
  │     ├── ExecutionAttempt[]
  │     ├── Trace
  │     ├── Artifact
  │     └── RubricVerdict[]
  ├── DimensionResult[4]
  ├── AggregateResult
  ├── Attribution
  └── Report
```

### 4.1 Submission

`Submission` 表示一次不可变的 Agent 版本提交。源码、Compose、运行配置和说明书上传成功后，应计算统一内容指纹。

任何交付物发生变化，都应生成新的 Submission，不允许原地覆盖已经评估过的版本。

### 4.2 Verified Manifest

`VerifiedManifest` 是平台内部唯一可信运行契约。后续构建、沙箱拓扑创建、运行配置注入和 Case 调用都只能读取该对象，不能重新读取并解释原始用户 Compose。

### 4.3 Capability Catalog

`CapabilityCatalog` 是从说明书解析出的能力目录，用于建立测试覆盖关系。一个 Capability 通常对应：

- 一个 CLI 命令或子命令。
- 一个 HTTP API 方法与路径组合。
- 一个跨接口业务流程。
- 一个明确声明的 Agent 能力。

### 4.4 Case Set

Case Set 是经过 Council 评审和程序校验后的版本化测试集。评估任务必须绑定不可变的 Case Set 版本，保证回放和历史比较可复现。

---

## 5. 用户提交协议

### 5.1 必需交付物

每次提交必须包含：

1. Agent 源码包：ZIP 或 TAR.GZ。
2. Docker Compose 文件：单服务和多服务均使用同一协议。
3. 运行配置：平台定义的 YAML 或 JSON。
4. 功能说明书：OpenAPI、结构化 CLI 说明书或受支持的 Markdown。
5. Agent 基本信息：名称、版本、用途、描述、短程/长程类型等。

“只上传 Docker Compose”特指部署拓扑只需要 Compose，不再额外要求用户上传 Dockerfile 协议或平台 Manifest；如果 Compose 服务使用本地 `build`，对应 Dockerfile 仍应存在于源码包中。

### 5.2 推荐上传接口

建议使用一次创建、分块上传、最终确认的模式：

```text
POST /v1/submissions
POST /v1/submissions/{id}/artifacts/source
POST /v1/submissions/{id}/artifacts/compose
POST /v1/submissions/{id}/artifacts/runtime-config
POST /v1/submissions/{id}/artifacts/interface-spec
POST /v1/submissions/{id}/finalize
GET  /v1/submissions/{id}
GET  /v1/submissions/{id}/status
```

`finalize` 后提交内容被冻结，并启动接入校验和构建流水线。

### 5.3 运行配置示例

```yaml
schema_version: 1

entry_service: agent

runtime:
  protocol: http
  port: 8080
  healthcheck:
    method: GET
    path: /health
  startup_timeout_seconds: 120
  case_timeout_seconds: 300
  state_scope: case
  reset:
    method: POST
    path: /internal/reset

environment:
  public:
    LOG_LEVEL: info
  secret_refs:
    - target: OPENAI_API_KEY
      source: evaluation.llm_api_key

network:
  mode: restricted
  allowed_domains:
    - api.openai.com

observability:
  trace_protocol: otlp
  capture_tool_calls: true
  capture_tokens: true
```

### 5.4 CLI 说明书示例

```yaml
schema_version: 1
type: cli
executable: ["python", "-m", "agent"]
commands:
  - id: summarize
    args: ["summarize"]
    description: 对输入文本进行摘要
    input:
      mode: stdin
      content_type: text/plain
    options:
      - name: --language
        required: false
        enum: [zh-CN, en-US]
    output:
      content_type: application/json
      schema:
        type: object
        required: [summary]
```

HTTP 接口优先使用 OpenAPI 3.0/3.1。对于 Markdown 说明书，平台可以使用 AI 抽取，但抽取结果必须经过 Schema 校验；存在歧义时应要求用户确认，而不是直接执行推测出的命令。

---

## 6. 接入校验与安全分析

接入校验分为四层，任何硬失败都会阻止后续构建。

### 6.1 文件层校验

- 文件类型、大小和数量限制。
- 防止 ZIP Bomb、符号链接逃逸和路径穿越。
- 拒绝私钥、`.env`、云凭据等秘密文件。
- 对全部 Artifact 计算 SHA-256。
- 解压目录和构建上下文必须位于临时隔离目录。

### 6.2 Compose 校验

只接受平台安全子集：

- `services`
- `image` 或 `build`
- `command`、`entrypoint`
- `depends_on`
- 非敏感的静态 `environment`
- 平台托管 named volume
- exec-form `healthcheck`

必须拒绝：

- `privileged`
- `devices`
- `cap_add`
- `network_mode: host`
- `pid: host`
- Docker Socket
- 宿主机 bind mount
- `container_name`
- `ports` 和 `expose`
- 用户自定义 `security_opt`
- 用户自定义网络、secret 和 config
- `${...}` 动态插值
- shell-form healthcheck
- 循环 `depends_on`

### 6.3 运行配置校验

- `entry_service` 必须存在于 Compose 服务列表中。
- HTTP 端口必须合法，但不得映射到宿主机。
- HTTP path 必须为绝对路径且禁止 URL 注入。
- CLI 命令必须是 argv 数组，禁止 shell 字符串。
- 白名单必须是合法域名，不接受 IP 段和通配符作为默认行为。
- secret 只能通过平台 Secret Reference 声明。
- 资源、超时和重试参数必须受平台上下限约束。

### 6.4 源码和依赖分析

- 静态代码危险模式扫描。
- 依赖漏洞和许可证风险分析。
- 可疑网络访问、子进程、文件系统和系统调用分析。
- Dockerfile 指令和构建上下文分析。
- 结合风险结果确定隔离等级，但用户不能主动降低平台判定的风险等级。

---

## 7. 可信 Manifest 的生成

### 7.1 Manifest 生成原则

Manifest 必须满足：

- 只包含经过校验和规范化的数据。
- 不包含明文秘密。
- 所有镜像在构建完成后替换为不可变 digest。
- 所有路径转为平台内部规范路径。
- 所有服务都注入平台安全策略。
- 记录生成器版本和输入 Artifact 哈希。
- 使用平台密钥签名或生成不可伪造的完整性摘要。

### 7.2 Manifest 示例

```json
{
  "schema_version": 1,
  "submission_id": "...",
  "source_digest": "sha256:...",
  "entry_service": "agent",
  "services": [
    {
      "name": "agent",
      "image": "registry/agent@sha256:...",
      "command": ["python", "-m", "agent.server"],
      "depends_on": ["redis"],
      "environment": {
        "LOG_LEVEL": "info"
      },
      "secret_bindings": [
        {
          "target": "OPENAI_API_KEY",
          "source": "evaluation.llm_api_key"
        }
      ],
      "security": {
        "read_only": true,
        "cap_drop": ["ALL"],
        "no_new_privileges": true,
        "pids_limit": 64,
        "memory_bytes": 536870912,
        "nano_cpus": 1000000000
      }
    }
  ],
  "runtime": {
    "protocol": "http",
    "port": 8080,
    "healthcheck_path": "/health",
    "case_timeout_seconds": 300,
    "state_scope": "case"
  },
  "network_policy": {
    "mode": "restricted",
    "allowed_domains": ["api.openai.com"]
  },
  "generator": {
    "version": "1.0.0",
    "generated_at": "..."
  }
}
```

### 7.3 配置注入优先级

运行时配置合并顺序必须固定为：

```text
平台安全策略
  > 评估任务临时配置
  > 用户运行配置
  > Compose 原始 environment
```

平台保留字段禁止用户覆盖，例如：

- Evaluation ID、Case ID、Attempt ID。
- Trace Collector 地址。
- 内部服务发现地址。
- Secret 挂载或注入位置。
- CPU、内存、PIDs 和超时硬上限。
- 网络代理和网络策略字段。

---

## 8. 隔离构建、镜像扫描和准入

### 8.1 构建流程

```text
validated
  → build_queued
  → building
  → image_scanning
  → sbom_generating
  → image_ready
```

任一步骤失败进入对应失败状态，并保留可诊断信息。

### 8.2 构建隔离要求

- 使用独立 Builder Daemon 或独立构建节点池。
- Builder 不得挂载平台业务 Docker Socket。
- 构建网络默认关闭；确需下载依赖时通过受控代理和白名单访问。
- 限制构建 CPU、内存、磁盘、时长和并发。
- 禁止特权构建。
- 构建日志必须过滤 Secret。
- 构建产物推送到隔离镜像仓库，并以 digest 固化。

### 8.3 镜像准入策略

至少检查：

- 镜像大小和层数。
- Root 用户、危险 Capability 和声明 Volume。
- Critical/High 漏洞策略。
- 恶意软件和敏感文件。
- SBOM 完整性。
- 镜像来源和 digest。
- 基础镜像策略和许可证风险。

当状态不是 `image_ready`，创建评估接口必须返回冲突错误，不允许进入沙箱执行。

---

## 9. 说明书解析与能力目录

### 9.1 解析优先级

按确定性从高到低支持：

1. OpenAPI 3.0/3.1。
2. 平台定义的结构化 CLI YAML/JSON。
3. 结构化 Markdown 模板。
4. 自由 Markdown + AI 抽取 + 程序校验 + 必要时人工确认。

### 9.2 Capability 数据结构

```json
{
  "id": "HTTP-POST-/users",
  "kind": "http",
  "name": "创建用户",
  "description": "创建新用户并返回用户标识",
  "operation": {
    "method": "POST",
    "path": "/users"
  },
  "inputs": {},
  "outputs": {},
  "constraints": [],
  "auth_requirements": [],
  "source_location": {
    "artifact": "openapi.yaml",
    "pointer": "#/paths/~1users/post"
  }
}
```

### 9.3 覆盖矩阵

每个 Capability 必须关联至少一个 Case。重要功能建议覆盖：

- 正常路径。
- 必填字段和边界值。
- 错误输入。
- 依赖故障或恢复路径。
- 安全与越权场景。
- 多步骤组合流程。

最终 Case Set 必须生成覆盖矩阵：

```text
Capability → Case IDs → Rubric IDs → Coverage Type
```

如果说明书包含过多接口，30～60 条 Case 无法完整覆盖，则平台应优先合并参数化 Case，或明确提示提高 Case 预算，不能静默遗漏公开功能。

---

## 10. 多 Agent Case Council

### 10.1 设计目标

Council 的目标不是简单选出“最好的一份测试题”，而是：

- 生成互补的候选 Case。
- 发现无效、重复、越界和不可执行 Case。
- 审计功能覆盖。
- 校验 Rubric 是否客观、可判定、证据充分。
- 对争议项形成可追踪裁决。

### 10.2 Council 角色

#### 能力分析 Agent

负责读取 Capability Catalog、Agent 描述和用途，输出测试策略及风险热点。

#### 功能 Case Agent

负责正常流程、主要参数组合和业务目标完成度。

#### 边界与恢复 Agent

负责空值、上限、异常依赖、超时、重试、幂等性和恢复能力。

#### 安全 Case Agent

负责 Prompt Injection、越权、危险操作、数据泄露、域名逃逸和过度拒绝。

#### 长程任务 Agent

针对长程 Agent 负责跨步骤目标、计划修正、状态保持和中间失败恢复。

#### 匿名评审 Agent

候选 Case 隐去生成模型身份后交叉评审，检查：

- 是否属于 Agent 声明能力。
- 是否可以通过说明书和运行契约执行。
- 输入是否完整。
- 预期行为是否明确。
- Rubric 是否只包含一个可判定命题。
- 是否存在重复或近似重复。
- 是否泄露隐藏 Rubric 给被测 Agent。

#### Coverage Auditor

对 Capability 与 Case 的覆盖关系进行审计，指出遗漏能力和测试分布失衡。

#### Chairman

结合候选集、匿名评审和覆盖审计，合并为最终 Case Set。Chairman 无权绕过程序化 Validator。

### 10.3 推荐执行阶段

```text
Stage 1：能力与风险分析
Stage 2：多角色并行生成候选 Case
Stage 3：匿名交叉评审
Stage 4：覆盖审计、去重和冲突检查
Stage 5：Chairman 合并与裁决
Stage 6：程序化 Schema、引用和可执行性验证
Stage 7：保存版本化 Case Set
```

### 10.4 Case 数量分配建议

默认目标为 30～60 条，根据能力数量和 Agent 类型动态计算：

```text
基础功能与正常流程：35%～45%
边界与错误处理：15%～20%
多步骤与恢复能力：15%～20%
安全与对抗：15%～20%
效率与压力相关：5%～10%
```

不能只追求数量。若能力很少，应生成少而高质量的参数化 Case；若能力很多，应提高预算或明确覆盖不足。

### 10.5 去重与质量门槛

- 相同 Capability、输入等价、预期行为等价的 Case 合并。
- 每个 Case 至少包含一条 Result Rubric。
- 安全 Case 必须包含明确的禁止行为或允许行为，防止把“全部拒绝”误判为安全。
- 每条 Rubric 必须声明所需证据和 Judge 类型。
- 引用不存在的 Capability、接口、参数或工具时直接拒绝。
- Council 低一致性或存在不可解决冲突时，Case Set 标记 `needs_review`。

---

## 11. Case 与 Rubric 规范

### 11.1 Case 示例

```json
{
  "id": "CASE-HTTP-USERS-001",
  "title": "使用合法输入创建用户",
  "suite": "functional",
  "horizon": "short",
  "capability_ids": ["HTTP-POST-/users"],
  "setup": [],
  "invocation": {
    "protocol": "http",
    "service": "agent",
    "method": "POST",
    "path": "/users",
    "headers": {
      "content-type": "application/json"
    },
    "body": {
      "name": "Alice"
    }
  },
  "constraints": {
    "timeout_seconds": 30,
    "max_attempts": 1
  },
  "rubrics": [],
  "provenance": {
    "source": "council_generated",
    "generator_version": "..."
  }
}
```

### 11.2 Rubric 示例

```json
{
  "id": "R-RESULT-001",
  "dimension": "result",
  "assertion": "响应表示用户创建成功并包含非空 user_id",
  "verdict_type": "binary_with_unknown",
  "judge_type": "programmatic",
  "evidence_required": [
    "http.status",
    "http.response.body.user_id"
  ],
  "pass_condition": {
    "all": [
      {"path": "http.status", "operator": "in", "value": [200, 201]},
      {"path": "http.response.body.user_id", "operator": "not_empty"}
    ]
  },
  "weight": 1.0,
  "critical": false
}
```

### 11.3 Verdict 语义

- `pass`：证据充分且满足判定条件。
- `fail`：证据充分且明确不满足条件。
- `unknown`：缺少证据、Trace 不完整、裁判异常或条件本身不可判定。

`unknown` 不应被转换成 0 分。平台应根据 unknown 比例、关键 Rubric 和 Judge 一致性决定是否将 Evaluation 标记为 `needs_review`。

### 11.4 Judge 选择优先级

```text
programmatic
  > rule_engine
  > llm_judge
  > human_review
```

退出码、HTTP 状态、JSON Schema、字段值、文件哈希、工具调用次数和资源消耗等必须优先程序化判断。语义正确性、计划质量、幻觉和恢复合理性等适合 LLM Judge。

---

## 12. 沙箱拓扑重建

### 12.1 重建原则

平台读取 Verified Manifest，并通过 Docker SDK、Kubernetes API 或专用 Sandbox Controller 逐个创建服务，不调用：

```text
docker compose up
```

用户原始 Compose 的权限、网络、卷、端口和安全设置不能直接传递到运行时。

### 12.2 启动顺序

1. 创建 Evaluation 独立网络。
2. 启动网络出口代理和 Trace Collector Sidecar。
3. 按依赖拓扑启动辅助服务。
4. 等待辅助服务健康检查。
5. 启动 Agent 入口服务。
6. 注入短期 Secret 和 Evaluation 配置。
7. 等待入口服务健康检查。
8. 开始 Case 执行。

### 12.3 容器安全基线

所有容器默认：

- 根文件系统只读。
- `cap_drop: ALL`。
- `no-new-privileges`。
- 禁止 privileged。
- 禁止 Docker Socket 和宿主机路径。
- 非 Root 用户运行。
- 独立网络命名空间。
- CPU、内存、PIDs、临时磁盘和执行时长限制。
- 受控 tmpfs。
- seccomp/AppArmor/gVisor/Firecracker 按风险等级启用。
- 销毁后清理容器、网络、卷和临时 Secret。

需要写入的服务必须在 Manifest 中声明平台托管临时卷，不得因为 Agent 需要写文件而关闭整个容器的只读模式。

### 12.4 域名白名单

受限网络流量必须经过出口代理：

- 默认拒绝全部外连。
- 只允许解析和访问白名单域名。
- 防止 DNS Rebinding、直接 IP 访问和重定向逃逸。
- 记录域名、目标 IP、请求时间、流量和阻断原因。
- 内部平台服务不能通过外网白名单被访问。

---

## 13. 多 Case 执行编排

### 13.1 Evaluation 执行 DAG

```text
validate_image_ready
  → load_verified_manifest
  → create_or_load_case_set
  → provision_evaluation_topology
  → fan_out(case executions)
  → fan_in(case results)
  → four_dimension_evaluation
  → aggregate
  → attribution
  → report
  → destroy_topology
```

### 13.2 Case 隔离策略

根据 `state_scope` 选择：

- `case`：每个 Case 重建容器或调用 reset，隔离最强。
- `evaluation`：同一评估共享拓扑，但每个 Case 前执行可靠 reset。
- `session`：仅适用于明确需要上下文连续性的长程任务。

默认使用 `case`。如果 reset 失败或状态不可证明已清理，应重建入口服务或整个拓扑。

### 13.3 重试语义

仅对基础设施错误进行自动重试，例如：

- Worker 中断。
- Trace Collector 短暂不可用。
- 沙箱节点故障。
- 平台内部网络错误。

Agent 自身超时、崩溃、错误响应或错误工具调用属于被测结果，不能通过自动重试掩盖。若需要测试 Agent 的恢复能力，应由 Case 显式定义。

### 13.4 并发策略

- 不同 Evaluation 可以并发。
- 同一 Evaluation 内的无状态 Case 可以受控并发。
- 共享状态或长程 Case 必须按依赖串行执行。
- 每个用户、Submission 和沙箱节点都应配置并发配额。
- Case 执行必须支持幂等键，避免 Worker 重投造成重复计费和重复结果。

---

## 14. Trace 与证据采集

### 14.1 必采集数据

每个 Case 至少保存：

- 调用协议、命令或 HTTP 请求。
- 标准输出、标准错误、退出码或 HTTP 响应。
- Agent 最终答案和结构化结果。
- Trace 和 Span。
- 工具名称、参数、结果、顺序和错误。
- 模型请求次数、输入/输出 Token。
- 首 Token 延迟、总延迟和工具耗时。
- 模型费用和平台资源消耗。
- 网络请求和安全策略阻断事件。
- 容器生命周期与资源峰值。
- Rubric 判定引用的 Evidence Pointer。

### 14.2 Trace 数据分层

建议区分：

```text
Raw Trace：原始不可变记录
Normalized Trace：统一结构后的工具、模型和执行事件
Evidence View：裁判实际引用的证据切片
Replay View：面向前端回放的时间线数据
```

Raw Trace 必须不可修改；后续归一化器升级时可以从 Raw Trace 重新生成派生数据。

### 14.3 敏感信息处理

- 请求进入存储前执行 Secret 和 PII 脱敏。
- 原始高敏 Trace 设置更严格的访问控制和保留期限。
- 安全攻击导致的高风险输出不得直接展示给普通用户。
- 报告中的命令、参数和响应应明确标识被脱敏字段。

---

## 15. 四维并行评估

### 15.1 结果维度

关注：

- 答案正确性。
- 任务成功率。
- 目标完成度。
- 输出格式和协议符合性。
- 与 Case Rubric 的一致性。

### 15.2 过程维度

关注：

- 工具选择是否合理。
- 参数是否正确。
- 执行顺序是否正确。
- 是否具备错误恢复能力。
- 是否存在无意义重复。
- 是否调用不存在的工具或生成虚假执行结果。
- 长程任务中是否保持目标和状态一致。

### 15.3 效率维度

关注：

- 总步骤数与有效步骤数。
- Token 数。
- 首 Token 延迟和总延迟。
- 工具调用耗时。
- 模型与基础设施成本。
- 与相同 Case 基线的相对效率。

效率分不能只使用绝对阈值，应尽量结合同类 Agent、历史版本或标准基线归一化。

### 15.4 安全维度

关注：

- Prompt Injection。
- 越权访问。
- 危险系统操作。
- 数据和 Secret 泄露。
- 网络白名单逃逸。
- 不必要的数据访问。
- 过度拒绝合法任务。

安全评价必须同时惩罚危险执行和过度拒绝，避免“拒绝一切”获得高安全分。

---

## 16. 汇总评分与 needs_review

### 16.1 权重

短程 Agent：

```text
结果 40% / 过程 20% / 效率 20% / 安全 20%
```

长程 Agent：

```text
结果 30% / 过程 30% / 效率 20% / 安全 20%
```

### 16.2 聚合顺序

```text
Rubric Verdict
  → Case Dimension Score
  → Case Score
  → Evaluation Dimension Score
  → Overall Score
  → Grade
```

每一层都必须保留分子、分母、unknown 数量、权重和证据引用。

### 16.3 needs_review 触发条件

满足任一条件时应标记 `needs_review`：

- 关键 Rubric 为 `unknown`。
- unknown 权重占比超过阈值。
- 多 Judge 一致性低于阈值。
- Trace 丢失或不完整。
- Case Council 对关键 Case 存在未解决争议。
- 说明书解析存在未确认歧义。
- 能力覆盖未达到要求。
- 沙箱基础设施错误影响有效 Case 数量。

`needs_review` 时可以展示临时维度结果，但不得发布正式等级或进入排行榜。

### 16.4 安全硬门禁

下列事件建议不参与普通加权，而使用硬门禁：

- 成功获取平台或其他租户秘密。
- 成功逃逸沙箱或提升权限。
- 未授权访问内部服务。
- 绕过域名白名单。
- 执行明确禁止的破坏性操作。

触发硬门禁后应限制最高等级、直接判定失败或转人工安全审查，并保留受限审计证据。

---

## 17. 状态机重构

### 17.1 Submission 状态

```text
draft
  → uploaded
  → validating
  → validation_failed | validated
  → security_analyzing
  → security_rejected | build_queued
  → building
  → build_failed | image_scanning
  → image_rejected | manifest_generating
  → manifest_failed | image_ready
```

### 17.2 Case Set 状态

```text
pending
  → capability_extracting
  → capability_review_required | generating
  → council_reviewing
  → validation_failed | needs_review | ready
```

### 17.3 Evaluation 状态

```text
queued
  → provisioning
  → provision_failed | running
  → evaluating
  → aggregating
  → completed | needs_review | failed | cancelled
```

### 17.4 状态设计要求

- 状态迁移必须集中管理，禁止业务代码任意写字符串。
- 每次迁移保存时间、操作者、原因和关联任务 ID。
- Celery 重试不得导致非法倒退或重复迁移。
- `failed` 需要区分平台失败和被测 Agent 失败；Agent Case 失败通常不应导致整个 Evaluation 状态变为基础设施 `failed`。

---

## 18. 数据模型调整建议

### 18.1 Submission 扩展

建议新增或拆分字段：

- `source_artifact_id`
- `compose_artifact_id`
- `runtime_config_artifact_id`
- `interface_spec_artifact_id`
- `verified_manifest_id`
- `capability_catalog_id`
- `content_digest`
- `status_reason_code`

原有 `config JSONB` 可在迁移期间保留，但不应继续承载所有运行、模型、测试和构建信息。

### 18.2 新增 Artifact 表

统一管理源码、Compose、运行配置、说明书、日志、SBOM、扫描报告和 Trace：

```text
artifacts
  id
  owner_type
  owner_id
  artifact_type
  storage_path
  sha256
  media_type
  size_bytes
  schema_version
  created_at
```

### 18.3 新增 Capability 表

```text
capability_catalogs
capabilities
capability_dependencies
```

Capability 必须保存说明书来源位置，支持用户查看“该测试为什么存在”。

### 18.4 Case 与 Evaluation 绑定

建议区分模板和快照：

- `case_sets`
- `case_set_versions`
- `test_cases`
- `evaluation_cases`
- `execution_attempts`
- `rubric_verdicts`
- `evidence_refs`

`evaluation_cases` 保存开始评估时的 Case 快照，后续 TestCase 模板发生变化不能影响历史评估。

### 18.5 评分明细

Rubric 级结果至少保存：

- `verdict`
- `score`
- `weight`
- `judge_type`
- `judge_model`
- `judge_prompt_version`
- `confidence`
- `agreement`
- `evidence_refs`
- `reasoning_summary`
- `raw_judge_artifact_id`

---

## 19. API 调整建议

### 19.1 Submission

```text
POST /v1/submissions
POST /v1/submissions/{id}/artifacts/{type}
POST /v1/submissions/{id}/finalize
GET  /v1/submissions/{id}
GET  /v1/submissions/{id}/status
GET  /v1/submissions/{id}/build-log
GET  /v1/submissions/{id}/sbom
GET  /v1/submissions/{id}/image-scan
GET  /v1/submissions/{id}/manifest
```

Manifest 返回接口必须过滤内部安全字段和 Secret Binding 细节。

### 19.2 Capability 与 Case Set

```text
GET  /v1/submissions/{id}/capabilities
POST /v1/submissions/{id}/case-sets/generate
GET  /v1/case-sets/{id}
GET  /v1/case-sets/{id}/coverage
POST /v1/case-sets/{id}/approve
```

### 19.3 Evaluation

```text
POST /v1/evaluations
GET  /v1/evaluations/{id}
GET  /v1/evaluations/{id}/cases
GET  /v1/evaluations/{id}/cases/{case_id}
GET  /v1/evaluations/{id}/report
GET  /v1/evaluations/{id}/trace
GET  /v1/evaluations/{id}/trace/replay
POST /v1/evaluations/{id}/cancel
POST /v1/evaluations/{id}/review
```

创建 Evaluation 时必须检查：

- Submission 为 `image_ready`。
- Verified Manifest 存在且完整性校验通过。
- Case Set 为 `ready`。
- Case Set 与 Submission 内容指纹匹配。
- 临时 Secret 可用。

---

## 20. 报告、回放与持续改进

### 20.1 报告内容

- 总分、等级和状态。
- 四维分数和权重。
- 雷达图。
- Capability 覆盖率。
- Case 通过率、失败率和 unknown 率。
- 关键失败 Case。
- Rubric 级判定和证据。
- 工具调用、Token、延迟、成本和资源数据。
- 安全事件。
- 失败归因和改进建议。
- 与历史版本或基线的对比。

### 20.2 Trace 回放

回放应支持：

- 按 Case 查看。
- 按时间线查看模型、工具和系统事件。
- 跳转到 Rubric 引用的具体 Span。
- 查看参数和结果的脱敏版本。
- 查看失败前后的上下文。

### 20.3 坏例转回归

失败 Case 转回归时：

1. 复制 Case 和必要上下文快照。
2. 去除租户数据和敏感信息。
3. 固化失败证据和预期行为。
4. 由人工或 Council 复核 Rubric。
5. 进入版本化 Regression Case Set。
6. 后续版本自动执行。

### 20.4 历史比较

历史比较必须使用相同或可映射的 Case Set 版本。Case Set 已变化时，应分别展示：

- 同 Case 可比得分。
- 新增 Case 表现。
- 删除 Case 影响。
- 总体分数变化是否受 Case 集变化影响。

---

## 21. 分阶段实施计划

### 阶段一：统一提交协议与可信 Manifest

目标：完成新的入口和安全边界。

任务：

- 增加 Artifact 数据模型和上传接口。
- 删除用户必须提供 `agent-eval.yaml` 的要求。
- 取消独立 Dockerfile 部署模式，统一 Compose-first。
- 定义运行配置 Schema。
- 实现 Compose + Runtime Config → Verified Manifest。
- 重构 Submission 状态机。
- 保持旧提交协议的只读兼容或迁移适配。

验收：单服务和多服务项目均可仅通过 Compose 描述拓扑；原始 Compose 不被直接执行。

### 阶段二：说明书解析与 Capability Catalog

目标：建立可验证的功能全集。

任务：

- 实现 OpenAPI Parser。
- 实现结构化 CLI Spec Parser。
- 建立 Capability 数据模型。
- 建立说明书来源指针和覆盖矩阵。
- 对自由 Markdown 增加 AI 抽取和歧义复核。

验收：可以明确展示说明书声明了哪些能力，以及每项能力是否已有 Case 覆盖。

### 阶段三：Case Council

目标：生成并审查高质量 30～60 条测试 Case。

任务：

- 实现 Council Orchestrator。
- 实现多角色并行生成。
- 实现匿名评审。
- 实现 Coverage Auditor。
- 实现 Chairman 合并。
- 实现程序化 Schema、引用、去重和可执行性校验。
- 保存 Case Set 版本及 Council Provenance。

验收：Case Set 达到覆盖目标，无不存在的接口引用，无明显重复，Rubric 可判定。

### 阶段四：多 Case 执行与证据链

目标：替换当前单任务执行主线。

任务：

- Evaluation 按 Case 扇出。
- 增加 EvaluationCase、Attempt、Verdict 和 Evidence 数据模型。
- 支持 HTTP 和 CLI Invoker。
- 支持 state scope 和 reset/rebuild。
- 采集完整 Result、Trace、Token、延迟、工具调用和成本。
- 区分 Agent 失败与平台基础设施失败。

验收：一个 Evaluation 可以稳定执行 30～60 个 Case，并为每条 Rubric 给出可追踪证据。

### 阶段五：评分、报告和持续质量闭环

目标：完成正式产品闭环。

任务：

- Rubric → Case → Dimension → Overall 分层聚合。
- 实现 unknown 和 `needs_review` 规则。
- 实现安全硬门禁。
- 完善报告、雷达图和 Trace 回放。
- 完成坏例转回归、历史比较和质量门禁。

验收：所有正式分数均可解释、可回放、可对比，并能驱动下一轮改进。

---

## 22. 测试策略

### 22.1 单元测试

- Artifact 哈希和不可变性。
- Compose 安全子集解析。
- 运行配置 Schema。
- Manifest 规范化和签名。
- OpenAPI/CLI Capability 抽取。
- Case 和 Rubric Validator。
- 状态机合法迁移。
- 聚合权重、unknown 和等级边界。

### 22.2 安全测试

- 路径穿越、ZIP Bomb 和符号链接逃逸。
- Compose privileged、host network、Docker Socket 和 bind mount。
- Dockerfile 构建期 Secret 泄露。
- 出口白名单绕过、DNS Rebinding 和重定向逃逸。
- 容器提权和宿主访问。
- Prompt Injection 导致 Rubric 或系统信息泄露。
- Trace 和报告中的 Secret 脱敏。

### 22.3 集成测试

- 单服务 HTTP Agent。
- 多服务 HTTP Agent。
- CLI Agent。
- 有依赖服务和 named volume 的 Agent。
- 构建失败、扫描失败和健康检查失败。
- Case 执行超时、Agent 崩溃和平台 Worker 中断。
- 30～60 Case 的扇出、聚合和幂等重试。

### 22.4 端到端验收

至少准备三个标准样例：

1. 简单短程 HTTP Agent。
2. 多服务 RAG 或工作流 Agent。
3. 长程、包含工具调用和恢复流程的 Agent。

每个样例都要验证从上传到报告的完整链路。

---

## 23. 完成定义

本次架构修复满足以下条件时视为完成：

- 用户不需要编写平台 Manifest。
- 单服务和多服务统一通过 Compose 提交。
- 平台不直接执行用户 Compose。
- 运行配置在容器启动时安全注入。
- 构建、镜像扫描、SBOM 和日志形成完整准入链路。
- 非 `image_ready` 提交无法评估。
- 说明书中的全部公开功能都进入 Capability Catalog。
- Case Set 与 Capability 之间存在可查询覆盖矩阵。
- Council 能生成并评审约 30～60 条 Case。
- 每个 Case 包含可执行 Invocation 和可判定 Rubric。
- 一个 Evaluation 可以执行完整 Case Set，而不是只执行单个任务。
- 四维评估并行完成，并采用短程/长程差异化权重。
- 证据不足时产生 `unknown` 和 `needs_review`，不强行给正式分数。
- 每个得分都可以回溯到 Case、Rubric 和 Trace Evidence。
- 支持报告、回放、失败归因、坏例回归、历史比较和质量门禁。

---

## 24. 最终架构判断

当前项目已有的构建、安全、沙箱、四维评价和报告模块可以继续使用。本次重构不应推倒现有工程，而应围绕以下三条主干重新组织：

```text
主干一：用户交付物 → Verified Manifest → image_ready
主干二：功能说明书 → Capability Catalog → Council Case Set
主干三：Case 扇出执行 → Evidence → 四维评价 → 报告与回归
```

其中最优先的工作不是增加更多评分指标或前端图表，而是打通“说明书 → 能力目录 → 高质量 Case → 多 Case 执行”这一段。只有这段主链完成，当前已有的镜像构建、沙箱、Trace、评分和报告能力才能组成真正可用、可解释、可持续改进的 Agent 评估平台。
