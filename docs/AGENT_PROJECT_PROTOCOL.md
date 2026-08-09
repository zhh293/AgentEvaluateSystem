# Agent 项目提交与评估协议 v2

本文档是新提交的规范性协议。平台只接受四个相互独立、内容不可变的 Artifact：

1. 源码包：ZIP、TAR.GZ 或 TGZ。
2. Docker Compose：单服务和多服务统一使用 Compose 声明拓扑。
3. Runtime Config：声明入口服务、调用协议、临时 Secret 和网络需求。
4. Interface Spec：OpenAPI 3.x 或平台结构化 CLI YAML/JSON。

用户不上传 `agent-eval.yaml`。平台校验四个 Artifact 后生成内部 Verified Manifest，并且绝不执行用户原始 Compose。

## 1. Artifact 与信任边界

源码、Compose、Runtime Config 和 Interface Spec 分别计算 SHA-256 并保存。提交完成后不可原地修改；任何 Artifact 变化都会形成新的 Submission。

```text
四个用户 Artifact（不可信）
       │
       ├─ 文件/路径/秘密检查
       ├─ Compose 安全子集解析
       ├─ Runtime Schema 校验
       └─ Interface Spec 确定性解析
       ▼
Verified Manifest（平台可信、内部使用）
```

后续构建、拓扑创建、配置注入和 Case 调用只读取 Verified Manifest，不再重新解释原始 Compose。

## 2. Compose 安全子集

允许 `services`、`image/build`、exec-form `command/entrypoint`、`depends_on`、静态非敏感 `environment`、平台托管 named volume 和 exec-form healthcheck。

拒绝 privileged、devices、cap_add、host network/PID/IPC、Docker Socket、宿主机 bind mount、ports、container_name、自定义 security_opt/network/secret/config、变量插值、shell-form命令和循环依赖。

Compose 服务使用本地 `build` 时，Dockerfile 和构建上下文位于源码包内。Dockerfile 只是 Compose 服务的构建细节，不再作为独立部署协议。

## 3. Runtime Config

```yaml
schema_version: 1
entry_service: agent
runtime:
  protocol: http                 # http | cli
  port: 8080
  healthcheck: { method: GET, path: /health }
  invoke_path: /v1/evaluations/run
  startup_timeout_seconds: 120
  case_timeout_seconds: 300
  state_scope: case              # case | evaluation | session
environment:
  public: { LOG_LEVEL: info }
  secret_refs:
    - target: OPENAI_API_KEY
      source: evaluation.llm_api_key
network:
  mode: restricted               # none | restricted
  allowed_domains: [api.openai.com]
```

公开环境变量不得包含疑似密钥。Secret 只允许通过受限引用声明，在 Evaluation 生命周期内从加密、带 TTL 的凭据保险库注入。Secret 不进入数据库 JSON、Manifest、构建参数、镜像层、日志或 Trace。

## 4. Interface Spec

HTTP Agent 使用 OpenAPI 3.0/3.1；CLI Agent 使用结构化 CLI Spec。说明书声明的每个 operation/command 都会形成 Capability，且每个 Capability 必须至少被一个最终 Case 覆盖。

CLI 示例：

```yaml
schema_version: 1
type: cli
executable: [python, -m, agent]
commands:
  - id: summarize
    args: [summarize]
    description: 对标准输入进行摘要
    input: { mode: stdin, content_type: text/plain }
    output: { content_type: application/json }
```

自由 Markdown 不是 v2 的直接执行协议。未来可以由 AI 抽取，但歧义必须先确认，不能让模型推测出的命令直接进入沙箱。

## 5. Case Council 与质量门禁

镜像达到 `image_ready` 后，至少三个独立 Council 成员按功能、边界恢复、安全和长程角色生成候选 Case；候选隐藏生成者身份后交叉评审，Chairman 合并为 30～60 条 Case。程序 Validator 最终检查：

- Capability 引用真实存在。
- HTTP method/path 或 CLI argv 与说明书精确匹配。
- 入口服务正确。
- Case 不重复。
- 每个 Case 至少一条 result Rubric。
- Rubric 原子化，Evidence Pointer 合法。
- 每个公开 Capability 至少被覆盖一次。

只有状态为 `ready` 的版本化 Case Set 可以创建 Evaluation。

## 6. 执行与证据

每个 Case 固化为 EvaluationCase 快照，并在平台根据 Verified Manifest 重建的独立拓扑中执行。所有容器使用只读根文件系统、非 Root 用户、`cap_drop=ALL`、`no-new-privileges`、资源限制、独立网络和受控临时卷。

平台保存每次 ExecutionAttempt、脱敏 Result、Case 级不可变 Trace Artifact、工具调用、Token、延迟、成本、Rubric Verdict 和 Evidence Pointer。Worker 重投会产生新 Attempt，不覆盖历史证据。

## 7. 评分语义

Rubric Verdict 为 `pass`、`fail` 或 `unknown`。unknown 不是零分；关键证据缺失、unknown 权重过高或 Judge 一致性不足时，Evaluation 标记为 `needs_review`，不发布正式等级。

短程权重为结果/过程/效率/安全 `40/20/20/20`，长程为 `30/30/20/20`。沙箱逃逸、密钥泄露、越权和网络策略绕过属于安全硬门禁，不能被其他维度的高分抵消。

