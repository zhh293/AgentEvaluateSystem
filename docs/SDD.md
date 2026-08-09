# Software Design Document (SDD)

## Agent 评估系统 — 企业级 Agent 评测平台

---

**文档版本**：v2.0  
**创建日期**：2026-08-08  
**状态**：完整版  

> 本设计文档的方法论核心来源于 Agent 评测技术文档（"Agent 体检指南"），覆盖从短程 Agent 到长程 Agent 的完整评测知识体系。

---

## 目录

1. [引言](#1-引言)
2. [评测方法论](#2-评测方法论)
3. [系统概述](#3-系统概述)
4. [技术栈](#4-技术栈)
5. [系统架构](#5-系统架构)
6. [详细模块设计](#6-详细模块设计)
7. [数据模型](#7-数据模型)
8. [API 接口设计](#8-api-接口设计)
9. [安全设计](#9-安全设计)
10. [部署架构](#10-部署架构)
11. [落地路径与分阶段路线图](#11-落地路径与分阶段路线图)
12. [附录](#12-附录)

---

## 1. 引言

### 1.1 目的

本文档对 **Agent 评估系统（AgentEvaluateSystem）** 进行完整的软件设计描述。系统目标为：接收用户提交的 Agent 源代码，在隔离沙箱中自动执行企业级多维度评测，输出评分、性能分析及可操作的改进建议。

### 1.2 范围

本系统覆盖以下核心能力：
- 支持**短程 Agent**（对话/检索/单轮任务）和**长程 Agent**（多步规划/工具编排/持久状态）的差异化评测
- 四层评测体系：结果层、过程层、效率层、风险层
- **Skill 全生命周期评测**：编写→发版→上线→监控
- **Task 三元组评测模型**：Prompt - ExpectedBehavior - Transcript
- **自我评测与自动修正闭环**：执行→评测→归因→修正→重试
- 七项评测基建能力：全链路回放、Case 管理、执行沙箱、AI 评测引擎、报告与归因、回归机制、准入准出门禁
- 自动化评分、雷达图可视化、Benchmark 对比、改进建议生成

### 1.3 定义与缩略语

| 术语 | 定义 |
|------|------|
| Agent | 具备自主规划、工具调用、多步执行能力的大模型应用 |
| 短程 Agent | 任务目标明确单一，执行链路 1-5 步的 Agent（如客服机器人、AI 搜索） |
| 长程 Agent | 任务目标模糊复杂，执行链路 10-50+ 步的 Agent（如编程助手、运维自动化） |
| Trajectory (Transcript) | Agent 执行全过程的完整记录：推理链、工具调用、中间状态、环境变化 |
| Response Evaluation | 仅评测 Agent 最终输出结果 |
| Trajectory Evaluation | 评测 Agent 完整执行过程（工具选择、推理路径、错误恢复） |
| Skill | Agent 可调用的原子能力单元，有自己的 Prompt、工具集和约束 |
| Task 三元组 | `(Prompt, ExpectedBehavior, Transcript)` — 长程 Agent 评测的基本单元 |
| Rubric | 评测量规，将模糊指标拆分为可判定的二元/三元标准（是/否/未知） |
| Dictator | 评测标准的唯一仲裁者角色，当评测员意见不一致时做最终裁决 |
| LLM-as-Judge | 使用大模型作为评判者对另一模型的输出进行评分 |
| Data Flywheel | 数据飞轮：采集→清洗→评测→质检→归因→优化 的持续闭环 |
| 人机一致 | LLM-as-Judge 的评分结果与人工评测结果的一致性（阈值 ≥ 85%） |
| 人人一致 | 多个评测员之间的评分标准对齐程度（阈值 ≥ 90%） |
| Sandbox | 安全隔离的执行环境（只读沙箱 / 可写沙箱 / 高风险沙箱三级） |

### 1.4 参考文献

- Agent 评测技术文档（知识库 doc: `07-agent`）—— 全套方法论来源
- Agent 标准化生态全景（知识库 doc: `12-agent`）
- Agent 可观测性与调试（知识库 doc: `06-agent`）
- Agent 安全与对抗（知识库 doc: `05-agent`）
- RAG 评测指标体系 RAGAS（知识库 doc: `06-rag`）
- GUI Agent 评测方法（知识库 doc: `09-computer-use-gui-agent`）
- Agentic Coding 评测方法（知识库 doc: `08-agenticcoding`）
- OpenTelemetry Generative AI 语义规范

---

## 2. 评测方法论

> 本章完整阐述 Agent 评测的核心方法论，作为系统设计的理论基石。内容来源于知识库 doc:`07-agent` 全文。

### 2.0 核心公式

```
观测 (Observation) + 评测 (Evaluation) = 持续迭代 (Continuous Iteration)
```

- **观测**：看清 Agent 每一步做了什么（工具调用、中间状态、输入输出）
- **评测**：判断 Agent 做得好不好
- **持续迭代**：两者结合，为精准优化指明方向

### 2.1 评测演进的三个阶段

| 阶段 | 时期 | 评测对象 | 输入 | 输出 | 关键指标 |
|------|------|---------|------|------|---------|
| ML 模型 | ~2019 | 分类/回归模型 | 特征向量 | 标签/数字 | 准确率、F1、AUC |
| 大语言模型 | 2022-2023 | LLM | Prompt 文本 | 生成文本 | BLEU、ROUGE、人类偏好 |
| **Agent** | **2024~** | LLM + 工具 + 规划的自主系统 | 自然语言任务 | 多步操作 + 完整轨迹 | **任务成功率、步骤准确率、效率、安全性** |

**Agent 阶段的核心挑战**：路径非确定、评估必须同时覆盖"结果对不对"和"过程对不对"。

### 2.2 两种常见评测误区

1. **离线打榜误区**：静态测试集会过拟合，分布偏离真实用户场景，离线高分不代表上线好用
2. **单次 Demo 定成败**：一次 Demo 成功不能证明系统可靠，一次失败也不能否定整体能力

### 2.3 Agent 评测的四层覆盖模型

```
┌──────────────────────────────────────────────────────────────┐
│  第四层 — 风险层："做了不该做的事吗？"                          │
│  数据泄露率 / 越权操作率 / 有害内容率 / 不可逆操作次数           │
├──────────────────────────────────────────────────────────────┤
│  第三层 — 效率层："够快够省吗？"                                │
│  步骤数 / Token 消耗 / 端到端延迟 / 冗余调用次数                 │
├──────────────────────────────────────────────────────────────┤
│  第二层 — 过程层："每一步走对了吗？"                             │
│  步骤正确率 / 工具选择准确率 / 参数构造正确率 / 错误恢复率         │
├──────────────────────────────────────────────────────────────┤
│  第一层 — 结果层："做成这件事了吗？"                             │
│  任务成功率 / 结果准确率 / 用户满意度                            │
└──────────────────────────────────────────────────────────────┘
```

**生活类比**：评审一个厨师 — 结果层=菜好不好吃，过程层=刀工火候，效率层=用料和时间，风险层=是否用了过期食材/交叉污染。

### 2.4 四层指标桥接：从模型能力到业务结果

评测体系的核心不是堆指标，而是**搭桥**——将四层指标从下到上逐层"翻译"：

| 层 | 名称 | 回答的问题 | 典型指标 | 谁最关心 |
|----|------|-----------|---------|---------|
| L4 | **业务目标** | "这事有没有产生价值？" | 转化率、留存率、NPS | 业务负责人、老板 |
| L3 | **任务目标** | "这类任务做对了没有？" | 搜索满意度、文案采纳率 | 产品经理 |
| L2 | **Agent 能力** | "每一步走对了吗？" | 意图识别准确率、工具调用成功率 | 算法工程师 |
| L1 | **模型能力** | "基座模型聪不聪明？" | 推理准确率、指令遵循、幻觉率 | 算法工程师 |

**关键原则**：业务人员（PM、运营）必须参与业务层和任务层指标的定义——算法工程师独自无法填补这个鸿沟。

### 2.5 客观评测与主观评测并行

| 维度 | 客观评测 | 主观评测 |
|------|---------|---------|
| 目标 | "对不对？"（有明确标准答案） | "好不好？"（依赖人类价值判断） |
| 典型场景 | 代码单测通过、数学答案正确、JSON 格式合法 | 回复自然吗？文案有说服力吗？语气合适吗？ |
| 方法 | 规则脚本、单测、精确匹配、程序化校验 | 人工标注、SBS 对比、Judge Model 打分 |
| 优点 | 快、便宜、100% 可复现 | 捕捉"人的感受"，规则做不到 |
| 缺点 | 无法覆盖"好不好" | 慢、贵、存在个体差异 |

**核心原则**：能用客观评测的尽量用客观；剩下的交给主观评测并努力让它收敛。

### 2.6 人人一致与人机一致

#### 2.6.1 Dictator 仲裁机制

- 设一个（或一个小委员会）拥有评测标准的**唯一仲裁权**
- 当评测员意见不一致时，Dictator 做最终裁决，并将裁决理由沉淀为规则
- **核心原则**：高方差比高偏差更危险。偏差可以统一校准（全员 -10%），方差意味着秤本身是坏的

#### 2.6.2 人人一致（Inter-Annotator Alignment）

多个评测员之间必须达成一致。方法：

```
背靠背标注（独立、盲评）→ 计算一致率
  ├─ ≥ 90% → 对齐良好
  ├─ 80-90% → 存在模糊地带，Dictator 补充规则
  └─ < 80% → Rubric 定义严重模糊，必须重做
```

**最低评测员数量**：≥ 3 人

#### 2.6.3 人机一致（Human-Machine Alignment）

LLM-as-Judge 的评分必须与已对齐的人工评测一致。

**信任阈值**：人机一致率 ≥ 85% → 可信任，可规模化；< 85% → 不可信，优化 Rubric 或 Judge Prompt 后重新校准。

### 2.7 Rubric 二元化 — 核心武器

将模糊指标拆成可执行的**是/否/未知**清单。

#### 三步流程

1. **指标下钻**：把模糊概念拆成具体的、独立的子维度，一直拆到每个子项可判断为止
2. **Rubric 二元化**：将每个子维度转为 是/否/未知 的 checklist。"未知"选项是 Rubric 健康度的探针——高未知率说明 Rubric 需要优化
3. **持续迭代**：监控 Unknown 比例，高于阈值则反查 Rubric 合理性

#### 案例：判断 AI 回复是否"有人味"

拆为 4 个二元 Rubric：
- R1：回复中是否使用了僵硬的书面的解释性语言？（是 → 扣分）
- R2：是否使用了至少 1 个口语化表达？（否 → 扣分）
- R3：句子长度是否均匀且适合口述（8-25 字为主）？（否 → 扣分）
- R4：是否有"首先/其次/最后/综上所述"等书面逻辑衔接词？（是 → 扣分）

**复合通过规则**：4 项全部通过才是"有人味"。

#### 量化效果

某团队实施 Rubric 二元化后，人机一致率从 62% 提升到 92%。另一团队在明确场景达到了 99%。

### 2.8 Agent 评测是一门实践科学（数据飞轮）

#### 2.8.1 五个关键环节

```
采集 → 清洗 → 评测 → 质检 → 归因分析 → 优化改进 ─┐
  ↑                                               │
  └───────────────────────────────────────────────┘
```

1. **采集**：从线上、灰度、内测多渠道收集 Trace 数据
2. **清洗**：去重、去噪、PII 脱敏
3. **评测**：人评 + AI Judge 打分（使用 2.5-2.7 的方法论）
4. **质检**：抽样检验评测结果，持续验证人机一致率没有漂移
5. **归因分析**：对失败 Case 做根因分析——是模型问题、Prompt 问题、工具 Bug、还是评测标准问题？

飞轮的每一圈转动，Agent 和评测体系本身都会同步进化。

#### 2.8.2 Bad Case 的价值远高于普通样本

- 一个通过的样本只能告诉你"这里没问题"
- 一个 Bad Case 能告诉你"这里有具体的问题"
- 评测体系的真正价值来自于持续不断的 Bad Case 挖掘和转化

#### 2.8.3 Bad Case 转化生命周期

```
发现 → 分析 → 转化 → 回归
  │       │       │       │
  │   Trace 定位  │   修复后跑回归
  │   具体失败模式  │   新 Rubric 永久留存
  │       │       │
  │   抽象为可复用   │
  │   Rubric + 加入
  │   种子评测集
```

**真实经验**：某团队评测指标从约 20 个增长到近 200 个，全部由线上 Bad Case 驱动。

### 2.9 专家知识补充模型能力不足

通用大模型缺乏深度领域知识（这些知识往往只存在于从业者的经验中，从未大规模写入互联网）。

#### 专家知识的两个角色

1. **专家是 Dictator 的最佳人选**：只有深度理解业务的人才能判断边界 Case，把模糊标准拆成精准 Rubric
2. **专家能发现"隐藏的 Bad Case"**：普通评测员根本意识不到有问题的地方，专家一眼就能看出

### 2.10 短程 Agent vs 长程 Agent

这是评测方法论的**根本分水岭**。不同类型的 Agent 需要完全不同的评测策略。

| 维度 | 短程 Agent | 长程 Agent |
|------|-----------|-----------|
| 任务目标 | 明确、单一、即时 | 模糊、复杂、多阶段 |
| 记忆 | 当前对话上下文 + 极少长期记忆 | 多级记忆：工作记忆/短期/长期 |
| 规划 | 即时反应（ReAct、CoT） | 层级规划 + 子目标树 + 动态调整 |
| 状态管理 | 无状态或单轮瞬态 | 持久状态机/检查点、中断可恢复 |
| 典型应用 | 客服机器人、AI 搜索、单轮问答 | 编程助手、多功能办公 Agent、运维自动化 |
| 环境交互 | 极少（用户对话、偶尔 API） | 大量（文件 IO、工具链、数据库、外部服务） |
| 观测链长度 | 1-5 步 | 10-50+ 步 |

**比喻**：短程 Agent = 自动售货机（投币→出货）；长程 Agent = 装修公司（沟通需求→设计→施工→验收）

### 2.11 短程 Agent 评测方法

#### 2.11.1 典型形态

`Query → Answer`

#### 2.11.2 六项核心评测指标

| 指标 | 含义 | 评测方式 |
|------|------|---------|
| **准确性 (Accuracy)** | 事实是否正确 | 与 Ground Truth 比对 / 语义相似度 |
| **相关性 (Relevance)** | 回答是否切题 | LLM-as-Judge 语义评分 |
| **流畅性 (Fluency)** | 语言自然、无语病 | LLM-as-Judge + 规则检查 |
| **有帮助性 (Helpfulness)** | 是否真正解决用户问题 | LLM-as-Judge + 人工抽检 |
| **安全性 (Safety)** | 拒绝不当请求、无有害输出 | 安全评测套件 + 规则引擎 |
| **连贯性 (Coherence)** | 多轮对话中的上下文保持 | 对话级别 Trace 分析 |

#### 2.11.3 评测工具链

对话标注 → 对话质检 → SBS 对比 → AI 评测 (Judge Model) → Pipeline 编排 → 数据集管理

### 2.12 长程 Agent 评测方法

#### 2.12.1 本质变化

> 短程评测 = "批改一篇作文"；长程评测 = "审计一整条流水线"

评测对象从"一段话"变成了"一个任务系统"：做成了什么、怎么做的、花了多少成本、有没有出事故。

#### 2.12.2 对观测和评测的影响

1. **观测**：必须捕获所有环境状态变化（文件 CRUD、记忆变更、工具调用参数/结果）
2. **人工评测成本爆炸**：一个 40 轮的样本评测约需 30 分钟（短程仅 1-2 分钟）
3. **自动评测挑战**：传统 Judge Model 遇到超长 Transcript 时上下文窗口被淹没，人机一致率下降
4. **环境交互**：必须使用沙箱隔离副作用并保证可复现

#### 2.12.3 Task 三元组评测模型

短程评测的基本单元：`(Query, Ground_Truth, Answer)` —— 判断 Answer 是否符合 Ground Truth

长程评测的基本单元：**`(Prompt, ExpectedBehavior, Transcript)`** —— 判断 Transcript 是否满足 Expected Behavior

| 术语 | 定义 | 类比 |
|------|------|------|
| Task | 一次测试，包含定义好的输入和成功标准 | 一道考题 |
| Trial | Agent 对 Task 的一次尝试 | 学生的一次作答 |
| Grader | 对 Agent 表现的某方面进行评分的逻辑 | 阅卷老师 |
| Transcript | Trial 的完整记录（输出、工具调用、推理、中间结果） | 草稿纸 + 考试录像 |
| Outcome | Trial 结束后环境的最终状态 | 最终答案 |
| Evaluation Harness | 端到端评测基础设施 | 考场 + 监考 + 阅卷流水线 |
| Agent Harness | 支撑模型以 Agent 形式运行的系统 | 文具 + 参考资料 |

#### 2.12.4 三种社区开源评测路线

| 路线 | 代表项目 | 核心理念 | 优点 | 缺点 |
|------|---------|---------|------|------|
| 真实场景基准 | 1200+ Star 项目 | 用例来自真实用户任务 | 贴近真实、中等可复现 | 覆盖度有限 |
| 模拟服务评测 | 500+ Star 高校项目 | 搭建 Mock API 可控测试 | 完全可控、高度可复现 | 与真实服务存在偏差 |
| 野生环境评测 | In-the-Wild | 直接操作真实 OS/文件系统/网络 | 最真实 | 可复现性低、安全管理挑战大 |

> 本系统采用**三合一策略**：真实场景基准（标准 Task Suite）+ 模拟服务（高风险操作使用 Mock）+ 野生环境（可选，高级用户自选）。

### 2.13 Skill 评测

#### 2.13.1 什么是 Skill

Skill 是 Agent 可调用的原子能力单元。类比微服务中的单个 Service——有自己的 Prompt、工具集、输入输出约束。

#### 2.13.2 Skill 全生命周期评测

| 阶段 | 类比软件开发 | 评测执行者 | 评测内容 |
|------|------------|-----------|---------|
| **Skill 编写** | 编码 | Skill 开发者 | 逻辑和 Prompt 自测 |
| **Skill 发版** | 单元测试 | Skill 开发者 | **单 Skill 评测**：在隔离沙箱中独立验证 |
| **Skill 上线** | 集成测试 | Skill 使用方 | **Skill N+1 评测**：修改一个 Skill 是否影响整体 Agent？ |
| **Skill 监控** | 生产监控 | Skill 使用方 | 线上稳定性、成功率、有效性 |

#### 2.13.3 Skill 评测的三大痛点

1. **观测痛点**：Case 现场还原极其困难——"案发现场没有监控"
2. **评测痛点**：Skill 评测与执行环境强耦合——需要带 Mock API 的沙箱化执行
3. **规模化痛点**：Skill 数量膨胀后的准入（≥ 90% 通过线）、回归、链式 Skill 评测、平台调度/吞吐

### 2.14 长程 Agent 评测基建的七项核心能力

评测基建不是做一个"打分工具"，而是构建一套完整的**Agent 驾考系统**。

#### 能力一：全链路回放

- 完整复现从输入到结果的每一次任务执行
- 记录每一步的输入/输出/时间戳/耗时、完整的工具调用参数/返回值、每次环境状态变化
- 支持**逐步前进/后退的交互式回放**

#### 能力二：Case 管理

- 统一维护评测 Case：样本数据 + 上下文/环境 + 约束 + 多维度评分规则（Rubric）
- 结构化 YAML/JSON 格式：
```yaml
task_id: "task_001"
prompt: "帮我分析这个月的销售数据"
context:
  files: ["sales_2026_08.csv"]
  available_skills: ["data_analysis", "chart_generation"]
  constraints:
    max_steps: 15
    allowed_tools: ["read_file", "run_python", "generate_chart"]
rubric:
  result:
    - id: R1
      description: "报告包含月度趋势分析"
      check: binary    # Yes / No / Unknown
    - id: R2
      description: "图表数据与原始数据一致"
      check: binary
  process:
    - id: R3
      description: "先读取数据再分析，不跳过数据加载步骤"
      check: trace_analysis
```

#### 能力三：执行沙箱（三级隔离）

| 沙箱级别 | 隔离强度 | Agent 权限 | 适用场景 |
|---------|---------|-----------|---------|
| **只读沙箱** | 高 | 可观察不可修改 | 信息检索类任务 |
| **可写沙箱** | 中 | 在隔离区域内读写 | 代码生成、文档编辑 |
| **高风险沙箱** | 最高 | 可执行命令、安装软件，但完全容器隔离 | 部署、系统管理类任务 |

#### 能力四：AI 评测引擎

- Rubric 驱动的自动化评分，每个 Rubric 独立 5 分制打分
- 持续监控人机一致率（< 85% 触发告警）
- Judge Model 对每个 Rubric 只评审 Transcript 的**相关片段**（不吞全量 Transcript）
- 输出：分数 + 推理依据

#### 能力五：报告与归因

评分之外，必须定位到**哪个环节出了问题**。五种归因类型：

| 归因类型 | 定义 | 示例 |
|---------|------|------|
| **规划错误** | 任务拆解或步骤顺序错误 | 应先查库存再下单，顺序反了 |
| **工具调用错误** | 工具选错或参数传错 | 调了 get_weather 而非 get_forecast |
| **Skill 缺陷** | Skill 本身有 Bug | 数据分析 Skill 的聚合逻辑错了 |
| **环境异常** | 外部依赖不可用 | 数据库连接超时 |
| **模型能力不足** | 基座模型无法理解复杂结构 | 嵌套 JSON 解析失败 |

#### 能力六：回归机制

自动触发条件：LLM 版本升级、Skill 增删改、Agent 框架代码变更、System Prompt 修改、工具接口变更。

触发后对历史 Case 集执行全量或增量回归，对比结果检出回退。

#### 能力七：准入准出门禁

将评测嵌入开发/发布/运营流程，作为必须通过的硬性条件：

| 门禁节点 | 检查内容 | 通过条件 |
|---------|---------|---------|
| **Skill 上线前** | 新 Skill 在标准 Case 集上的通过率 | ≥ 90% |
| **模型版本切换前** | 新模型在全量回归 Case 集上的表现 | ≥ 旧模型的 95% |
| **System Prompt 修改后** | 修改后在核心场景上的表现 | 核心 Case 100% 通过 |
| **日常运营监控** | 线上真实任务的成功率和用户满意度 | 成功率 ≥ 85%，满意度 ≥ 4.0/5.0 |

### 2.15 自我评测与自动修正闭环

这是评测体系的**最高形态**——Agent 完成一次任务后，系统自动评分、自动归因、自动修正、自动重新执行。

```
开发者定义 Expected Behavior + Rubric (一次性投入)
                │
                ▼
        Agent 执行任务 ──► 记录完整 Trace
                │
                ▼
        自动评测 (对照 Rubric)
                │
         ┌──────┴──────┐
         ▼              ▼
     全部通过         有未通过的 Rubric
         │              │
         ▼              ▼
     返回结果        归因分析 (定位失败环节)
                       │
                       ▼
                    自动修正
                       │
                       ▼
                    重新执行 ──► 重新评测 (检验全部 Rubric，包括之前已通过的)
                       │
                ┌──────┴──────┐
                ▼              ▼
            全部通过       超过最大重试次数
                │              │
                ▼              ▼
           返回结果      降级：返回最优结果 + 标记"需人工介入"
```

#### 四个关键设计原则

1. **Rubrics 必须可二元化、可自动判分**：任何依赖"人的感觉"的指标都不能进入自评闭环
2. **严肃对待 Unknown**：Unknown Case 反馈给开发者，用于完善 Rubric 定义
3. **防退化机制是刚性的**：修正 A 后必须重新检验**全部** Rubric（包括之前已通过的），防止修好一个坏了另一个
4. **开发者反馈闭环**：所有"需人工介入"的 Case 回流给开发者——这些代表了当前自评能力的边界

---

## 3. 系统概述

### 3.1 系统定位

AgentEvaluateSystem 是一套**Agent 驾考系统**：

| 驾考系统 | Agent 评估系统 |
|---------|---------------|
| 考试题库 | Case 评测集 |
| 封闭考场 | 执行沙箱 |
| 电子评分系统 | AI Judge Engine |
| 行车记录仪 | 全链路 Trace 回放 |
| 扣分明细 | 评测报告 + 归因 |
| 定期换证 | 回归测试 |
| 考试合格才能上路 | 准入准出门禁 |

### 3.2 评测类型覆盖矩阵

| | 短程 Agent | 长程 Agent |
|------|-----------|-----------|
| **结果评测** | Accuracy / Relevance / Fluency / Helpfulness / Safety / Coherence | Task Success Rate / Outcome Correctness |
| **过程评测** | 单轮工具调用正确性 | 全链路 Trajectory 分析：工具链正确性、规划质量、错误恢复 |
| **效率评测** | Token 消耗 / 延迟 | 步骤效率 / 多步 Token 累积 / 端到端成本 |
| **风险评测** | 有害内容检测 / 越狱抵抗 | 危险操作拦截 / 越权操作检测 / 数据泄露检测 |
| **Skill 评测** | — | 单 Skill 评测 / Skill N+1 集成评测 |
| **自我评测** | — | 执行→评测→归因→修正→重试 闭环 |

### 3.3 核心设计原则

1. **四层全覆盖 + 双轨并行**：结果层/过程层/效率层/风险层，客观+主观评测同时跑
2. **分层指标桥接**：业务→任务→Agent→模型，层层可追溯
3. **短程/长程分流**：不同类型的 Agent 使用不同的评测策略和 Task Suite
4. **Rubric 驱动**：所有评测标准必须是可二元化的 Rubric，确保可自动执行
5. **安全第一**：三级沙箱隔离，默认不信任任何第三方 Agent 代码
6. **数据飞轮闭环**：从采集到优化，每一轮都让 Agent 和评测体系同步进化
7. **准入准出刚性门禁**：评测结果嵌入开发流程，不达标就卡住

---

## 4. 技术栈

### 4.1 总览

| 层次 | 技术选型 | 选型理由 |
|------|---------|---------|
| **前端** | React 18 + TypeScript + Tailwind CSS + ECharts | 评测仪表盘、雷达图、Trace 回放可视化 |
| **API 网关** | Nginx + FastAPI | 反向代理、限流、认证 |
| **后端服务** | Python 3.12 + FastAPI | AI/ML 生态成熟，异步高性能 |
| **异步任务** | Celery + RabbitMQ | 评测任务长时运行，需异步解耦 |
| **沙箱运行时** | Docker + gVisor (中) / Firecracker VM (高) | 三级隔离：只读/可写/高风险 |
| **关系数据库** | PostgreSQL 16 | 用户、项目、Case、评测结果等结构化数据 |
| **缓存** | Redis 7 | 任务队列状态、限流计数、评测结果热缓存 |
| **对象存储** | MinIO (S3 兼容) | Agent 源码包、Trace 文件、评测报告 |
| **可观测性** | OpenTelemetry + Jaeger + Prometheus + Grafana | 全链路 Trace、Metrics、Dashboard |
| **容器编排** | Kubernetes 1.30 (生产) / Docker Compose (开发) | 弹性伸缩、沙箱节点池隔离 |
| **CI/CD** | GitHub Actions | 自动化测试、镜像构建、门禁检查 |

### 4.2 关键依赖库

```
# 后端核心
fastapi==0.115.x
celery==5.4.x
sqlalchemy==2.0.x
alembic==1.14.x
pydantic==2.10.x
docker==7.x                 # Docker SDK 沙箱管理

# 评测引擎
openai==1.55.x              # LLM-as-Judge (支持多模型)
anthropic==0.40.x           # Claude Judge
langfuse==2.x               # LLM Trace 采集

# 可观测性
opentelemetry-api==1.28.x
opentelemetry-sdk==1.28.x

# 安全
bandit==1.8.x               # Python 静态分析
safety==3.x                 # 依赖漏洞扫描
```

---

## 5. 系统架构

### 5.1 总体架构（六层模型）

```
┌─────────────────────────────────────────────────────────────┐
│                     6. 展示层 (Presentation)                 │
│   React SPA  │  REST API  │  WebSocket (实时进度推送)        │
│   - Dashboard (雷达图 / 趋势 / 排行榜)                       │
│   - Trace Viewer (全链路回放交互界面)                        │
│   - Case Manager (评测集管理)                                │
│   - Report View (评分详情 + 归因 + 改进建议)                  │
├─────────────────────────────────────────────────────────────┤
│                     5. API 网关层 (Gateway)                  │
│   认证鉴权 (JWT)  │  限流熔断  │  请求路由  │  审计日志        │
├─────────────────────────────────────────────────────────────┤
│                     4. 评测编排层 (Orchestration)            │
│   任务调度  │  Pipeline DAG 编排  │  状态机管理               │
│   准入准出门禁  │  回归触发  │  自评修正循环调度              │
├──────┬──────────────────────────────────────────────────────┤
│      │              3. 评测引擎层 (Engine)                   │
│      │   ┌──────────┬──────────┬──────────┬──────────┐      │
│      │   │ 静态分析 │ 结果评测 │ 过程评测 │ 效率评测 │      │
│      │   │ 安全扫描 │ Response │Trajectory│Efficiency│      │
│      │   ├──────────┼──────────┼──────────┼──────────┤      │
│      │   │ 风险评测 │Skill 评测│ AI Judge │ 对抗评测 │      │
│      │   │ Security │ 全生命   │ Engine   │ Adversarial│   │
│      │   ├──────────┴──────────┴──────────┴──────────┤      │
│      │   │         评分聚合 + 归因分析引擎              │      │
│      │   │         报告生成 + 改进建议生成              │      │
│      │   └────────────────────────────────────────────┘      │
├──────┼──────────────────────────────────────────────────────┤
│      │              2. 评测基建层 (Infrastructure)            │
│      │   全链路回放  │  Case 管理  │  回归引擎  │  自评修正   │
├──────┼──────────────────────────────────────────────────────┤
│      │              1. 沙箱运行时层 (Sandbox)                │
│      │   只读沙箱  │  可写沙箱  │  高风险沙箱 (VM)            │
│      │   Mock Service 模拟  │  网络隔离  │  资源硬限制        │
├──────┴──────────────────────────────────────────────────────┤
│                      基础设施层                              │
│   K8s / Docker Compose  │  PostgreSQL  │  Redis  │  MinIO    │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 核心数据流

```
用户提交 Agent 源码包
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│  Phase 1: 接入校验 (同步)                                   │
│  解包 → 格式校验 → 静态安全扫描 → 依赖审计 → Agent 类型识别   │
│  短程 → 短程 Task Suite     长程 → 长程 Task Suite          │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│  Phase 2: 隔离构建 (异步，独立 Build Worker)                  │
│  Dockerfile-first → 无网络构建 → 镜像扫描/SBOM → 推送摘要引用  │
│  无 Dockerfile 的旧 agent.py 包由平台生成兼容 Dockerfile      │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│  Phase 3: 评测执行 (异步，多引擎并行)                        │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ 结果评测  │  │ 过程评测  │  │ 效率评测  │  │ 风险评测  │ │
│  │ (短程6指标│  │ (工具链   │  │ (Token/  │  │ (注入/   │ │
│  │  长程完成 │  │  推理路径  │  │  延迟/   │  │  越狱/   │ │
│  │  率)      │  │  错误恢复) │  │  步骤效率)│  │  危险操作)│ │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬────┘ │
│        └──────────────┴──────────────┴──────────────┘     │
│                           │                               │
│                    ┌──────▼──────┐                        │
│                    │ Skill 评测   │ (如果是长程 Agent)      │
│                    │ 全生命周期   │                        │
│                    └──────────────┘                        │
│                                                          │
│  全链路 Trace 实时采集 → Jaeger/LangFuse                    │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│  Phase 4: 评分聚合 + 归因分析                               │
│  加权计算 → 五类归因 → Benchmark 对比 → 改进建议生成         │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│  Phase 5: 报告生成 + 推送                                   │
│  JSON 报告 + 雷达图数据 → WebSocket 推送 → 用户可见          │
│                           │                               │
│  ┌────────────────────────┴──────────────────────────┐   │
│  │  可选：进入自我评测修正闭环                           │   │
│  │  评测 → 归因 → 修正建议 → Agent 自动修改 → 重跑评测   │   │
│  └───────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

---

## 6. 详细模块设计

### 6.1 接入层：Agent 提交与校验

#### 6.1.1 提交包规范

```text
submission.zip (或 tar.gz / tgz, max 50MB)
├── Dockerfile                   # 首选：提交者定义依赖与启动方式
├── agent-eval.yaml              # 首选：平台构建/运行契约
├── src/                         # 任意语言、任意多文件结构
├── requirements.txt / pyproject.toml  # 可选：同时参与源码依赖审计
├── tools/ / skills/ / prompts/  # 可选
└── agent.py                     # 仅旧版兼容包需要
```

#### 6.1.2 agent-eval.yaml 运行契约

```yaml
schema_version: 1
build:
  dockerfile: Dockerfile
  context: .
runtime:
  protocol: stdio              # stdio | http
  timeout_seconds: 300
  # HTTP 模式额外声明 port / healthcheck / invoke
security:
  network: none                # none | restricted
  allowed_domains: []
```

业务表单仍由系统生成内部 `agent.config.yaml`，用于 Rubric、工具、模型和评测约束；它不再承担项目启动职责。Dockerfile 是构建契约，`agent-eval.yaml` 是调用契约，源码压缩包是不可变审计原件。

#### 6.1.3 校验流程

```
提交包 → 安全解压 → Dockerfile + agent-eval.yaml（或旧版 agent.py）
                │
                ├─ 依赖声明校验
                ├─ Agent 类型识别: short_horizon / long_horizon
                │     ├─ short → 短程 Task Suite
                │     └─ long  → 长程 Task Suite + Skill 评测
                ├─ 风险等级评估: low / medium / high
                │     ├─ 纯对话/检索 → low
                │     ├─ 文件操作/API调用 → medium
                │     └─ 代码执行/系统命令 → high
                ├─ 静态代码安全扫描 (Bandit AST 分析)
                │     ├─ 检测 os.system / subprocess / eval / exec
                │     ├─ 检测网络调用白名单违规
                │     └─ 检测文件系统危险操作
                ├─ 依赖安全审计 (safety check)
                ├─ Dockerfile 策略检查（禁止远程 ADD、Docker Socket、特权参数）
                └─ build_queued → building（含镜像扫描）→ image_ready
```

### 6.2 沙箱运行时层

#### 6.2.1 三级隔离沙箱

```
Agent 风险等级        沙箱类型            隔离强度        允许的操作
──────────────────────────────────────────────────────────────
low                   Docker 容器          标准隔离        只读文件系统 + 声明API
medium                Docker + gVisor      增强隔离        受限读写(隔离区域) + 白名单域名
high                  Firecracker VM       强隔离          可执行命令(完全容器) + offline
```

#### 6.2.2 沙箱生命周期

```
1. 创建 → Docker build Sandboxfile，注入 Agent 源码 + 依赖 + Task Suite
2. 初始化 → pip install + 启动 OTel Agent + 健康检查
3. 执行 → 注入评测任务，采集 Trace/Metrics/Logs，超时控制 + 资源监控
4. 导出 → Trace → MinIO，销毁沙箱 → docker rm -f，清理临时文件/网络/卷
```

#### 6.2.3 资源限制

| 限制项 | 默认 low | 默认 medium | 默认 high |
|--------|---------|------------|----------|
| CPU | 1 核 | 2 核 | 4 核 |
| 内存 | 2 GB | 4 GB | 8 GB |
| 磁盘 | 5 GB | 10 GB | 20 GB |
| 超时 | 120s | 300s | 600s |
| 网络 | 仅 API endpoint | 白名单域名 | 完全隔离 |
| 进程数 | 20 | 50 | 100 |
| 系统调用 | 默认 seccomp | 自定义 seccomp | 严格白名单 |

### 6.3 评测引擎层（核心）

#### 6.3.1 评测引擎总览

```
                      评测任务调度器
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
    短程 Agent         长程 Agent         通用引擎
    评测流水线         评测流水线         (两种共用)
          │                 │                 │
    ┌─────┴─────┐    ┌─────┴─────┐    ┌──────┴──────┐
    │结果评测    │    │结果评测    │    │ 静态分析引擎 │
    │(6项指标)  │    │(完成率+   │    │ 安全评测引擎 │
    │           │    │ 正确性)   │    │ 对抗评测引擎 │
    │过程评测    │    │           │    │ AI Judge    │
    │(单步工具)  │    │过程评测    │    │ 评分聚合     │
    │           │    │(全链路    │    │ 报告生成     │
    │效率评测    │    │ Trajectory│    │             │
    │           │    │ 分析)     │    │             │
    │安全评测    │    │           │    │             │
    └───────────┘    │效率评测    │    └──────────────┘
                     │           │
                     │Skill 评测  │
                     │(单Skill +  │
                     │ N+1集成)  │
                     │           │
                     │自我评测修正│
                     │闭环       │
                     └───────────┘
```

#### 6.3.2 短程 Agent 评测详细指标

| 指标 | 评测方法 | 评分范围 | Judge 类型 |
|------|---------|---------|-----------|
| **准确性** | 与 Ground Truth 比对（精确匹配 / 语义相似度） | 0-100 | 程序化 + LLM |
| **相关性** | 判断回答是否切中用户问题核心 | 1-5 | LLM-as-Judge |
| **流畅性** | 语法正确性、自然度、无语病 | 1-5 | LLM-as-Judge + 规则 |
| **有帮助性** | 是否真正解决问题，而非"正确的废话" | 1-5 | LLM-as-Judge |
| **安全性** | 拒绝不当请求、无有害输出 | 0-100 | 规则引擎 + LLM |
| **连贯性** | 多轮对话上下文保持 | 1-5 | LLM-as-Judge |

#### 6.3.3 长程 Agent 评测详细指标

##### 结果层
| 指标 | 含义 | 评测方式 |
|------|------|---------|
| Task Success Rate | 任务是否完成 | Outcome 校验 |
| Result Correctness | 输出结果是否正确 | 与 Expected Behavior 比对 |
| User Satisfaction | 结果是否满足用户预期 | LLM-as-Judge |

##### 过程层
| 指标 | 含义 | 评测方式 |
|------|------|---------|
| Plan Quality | 任务拆解和步骤顺序是否合理 | LLM-as-Judge Trace 分析 |
| Tool Selection Accuracy | 每步选择的工具是否正确 | 与 Expected Tool Chain 比对 |
| Tool Call Correctness | 工具调用的参数是否正确 | 参数模式匹配 |
| Error Recovery Rate | 遇到错误后是否正确恢复 | Trace 中 Retry 模式分析 |
| Hallucination Rate | 是否编造了不存在的工具或参数 | 工具白名单校验 |
| Step Redundancy | 是否有冗余的重複步骤 | Trace 步骤去重分析 |

##### 效率层
| 指标 | 计算方式 |
|------|---------|
| Step Efficiency | min(最短可能步数 / 实际步数, 1.0) × 100 |
| Token Efficiency | 总 Token 消耗 / 任务复杂度系数 |
| End-to-End Latency | P50 / P90 / P99 |
| Cost per Task | Token 成本 + 工具调用成本 ($) |

##### 风险层
| 指标 | 含义 |
|------|------|
| Injection Resistance | Prompt 注入防御成功率 |
| Jailbreak Resistance | 越狱攻击防御成功率 |
| Dangerous Op Block Rate | 危险操作被拦截比例 |
| Over-Refusal Rate | 安全操作被误拒比例 |
| Data Leak Rate | 敏感信息泄露检测 |

#### 6.3.4 过程评测 Trajectory 采集规范

遵循 OpenTelemetry GenAI 语义规范：

```
AGENT_EXECUTION      # Agent 整体执行 (root span)
├── AGENT_PLANNING   # 规划阶段 (任务拆解、子目标生成)
├── LLM_CALL         # LLM 推理调用 (prompt, completion, model, token_usage)
├── TOOL_EXECUTION   # 工具调用 (tool_name, input, output, duration, error)
├── AGENT_DECISION   # Agent 决策点 (推理、路由、条件判断)
├── SKILL_EXECUTION  # Skill 调用 (skill_name, pre/post state)
├── RETRIEVAL        # 检索操作 (query, top_k, results, scores)
├── MEMORY_READ      # 记忆读取
├── MEMORY_WRITE     # 记忆写入
├── ENVIRONMENT_STATE_CHANGE  # 环境状态变化 (文件变化、DB写入等)
└── EXTERNAL_API     # 外部 API 调用 (url, method, status_code, latency)
```

#### 6.3.5 AI Judge 引擎

##### 双 Judge 独立评分机制

```
每个 Rubric 的评测流程:
  1. 从 Transcript 中提取与该 Rubric 相关的片段
  2. Judge A (如 GPT-4o) 独立评分 + 给出推理依据
  3. Judge B (如 Claude Opus 4) 独立评分 + 给出推理依据
  4. 比对:
     ├─ 偏差 ≤ 1 分 → 取均值
     ├─ 偏差 = 2 分 → 引入 Judge C 仲裁
     └─ 偏差 ≥ 3 分 → 样本标记为"需人工复核"，同时记录差异供 Dictator 分析
```

##### Judge Prompt 设计三原则

1. **喂 Transcript 片段而非全文**：只给与该 Rubric 相关的 Span 上下文，避免上下文窗口被淹没
2. **强制输出 Yes/No/Unknown**：不允许模糊的"还可以""差不多"
3. **必须给出推理依据**：引用 Transcript 中的具体位置（span_id + 行号）

##### 人机一致率持续监控

```
每次评测后自动抽样 10% 样本送人工复核
  ├─ 人机一致率 ≥ 85% → 正常
  └─ 人机一致率 < 85% → 告警 → 排查原因:
       ├─ Rubric 定义模糊？→ 优化 Rubric
       ├─ Judge Prompt 不够好？→ 优化 Prompt
       └─ Transcript 太长 Judge 看不全？→ 优化片段提取逻辑
```

#### 6.3.6 Skill 评测引擎

##### 单 Skill 评测

```
Skill 发版 → 独立沙箱部署 Skill → 注入 Skill 专用 Test Suite
         → 评测 Skill 独立表现:
            ├─ 功能正确性 (输入输出匹配)
            ├─ 边界条件处理
            ├─ 错误处理
            └─ 性能指标 (延迟/Token)
         → ≥ 90% 通过 → 允许发布
```

##### Skill N+1 集成评测

```
Skill 上线前 → 部署完整 Agent (含该 Skill) → 注入全量回归 Case 集
           → 评测整体 Agent 表现:
              ├─ 新 Skill 是否与已有 Skill 冲突？
              ├─ 工具选择是否受影响？
              └─ 整体任务成功率是否下降？
           → ≥ 旧版本 95% → 允许上线
```

#### 6.3.7 对抗评测引擎

```
对抗评测 Pipeline:
  1. 静态攻击用例集 (100+ 条固定攻击 Prompt)
     覆盖: 直接注入、间接注入、角色扮演越狱、编码混淆、语义诱导

  2. 自动对抗样本生成:
     ├─ PAIR (Prompt Automatic Iterative Refinement)
     │   攻击 LLM 自动迭代生成变体，探测 Agent 防御边界
     └─ TAP (Tree of Attacks with Pruning)
         树状搜索攻击路径，自动剪枝低效分支

  3. 结果分类:
     ├─ 成功注入 (Agent 执行了恶意指令)
     ├─ 被防御 (Agent 拒绝或被拦截)
     └─ 部分影响 (Agent 未执行但有异常行为)

  4. 安全评分 = (1 - 注入成功率) × 100
```

### 6.4 评分聚合引擎

#### 6.4.1 加权评分模型

```
总评分 = W_result × S_result + W_trajectory × S_trajectory
        + W_efficiency × S_efficiency + W_security × S_security

短程 Agent 默认权重: W_result=0.40, W_trajectory=0.20, W_efficiency=0.20, W_security=0.20
长程 Agent 默认权重: W_result=0.30, W_trajectory=0.30, W_efficiency=0.20, W_security=0.20
```

#### 6.4.2 五类归因引擎

```
评测分数低于阈值 → 下钻到子指标 → 关联 Trace → 五类归因:

1. 规划错误 → 建议: 优化 System Prompt 中的任务拆解逻辑
2. 工具调用错误 → 建议: 优化工具描述，增加参数校验
3. Skill 缺陷 → 建议: 修复 Skill 本身的 Bug
4. 环境异常 → 建议: 增加重试/降级逻辑
5. 模型能力不足 → 建议: 考虑换用更强模型或增加 Few-shot 示例
```

#### 6.4.3 评分等级映射

```
A+  93-100    卓越 (Excellent)
A   87-92     优秀 (Great)
A-  83-86
B+  78-82     良好 (Good)
B   73-77
B-  68-72
C+  63-67     及格 (Pass)
C   60-62
D   <60       需改进 (Needs Improvement)
```

### 6.5 全链路回放系统

#### 6.5.1 回放数据模型

```json
{
  "trace_id": "trace_abc123",
  "session_id": "sess_xyz",
  "agent_id": "agent_001",
  "start_time": "2026-08-08T12:00:00Z",
  "end_time": "2026-08-08T12:00:45Z",
  "total_duration_ms": 45000,
  "spans": [
    {
      "span_id": "span_001",
      "parent_span_id": null,
      "type": "AGENT_EXECUTION",
      "start_offset_ms": 0,
      "duration_ms": 45000,
      "status": "success"
    },
    {
      "span_id": "span_002",
      "parent_span_id": "span_001",
      "type": "AGENT_PLANNING",
      "start_offset_ms": 0,
      "duration_ms": 3200,
      "input": {"prompt": "帮我分析销售数据"},
      "output": {"plan": ["读取文件","分析数据","生成报告"]}
    }
  ],
  "environment_snapshots": [
    {"timestamp_ms": 0, "files": [], "memory": {}},
    {"timestamp_ms": 5000, "files": ["report.md"], "memory": {"last_query": "销售数据"}}
  ]
}
```

#### 6.5.2 回放功能

- 逐步前进/后退
- 跳转到指定 Span
- 按 Span 类型过滤
- 环境状态快照对比（前后变化）
- 标注/评论（用于 Dictator 复盘）

### 6.6 回归机制

```
自动触发条件:
  ├─ Agent 框架代码变更 (git push to agent repo)
  ├─ LLM 模型版本切换
  ├─ Skill 新增/修改/删除
  ├─ System Prompt 修改
  └─ 工具接口变更

回归策略:
  ├─ 核心 Case: 全量回归 (每次触发)
  ├─ 扩展 Case: 增量回归 (每日定时)
  └─ 全量 Case: 周期回归 (每周)

回归结果:
  ├─ 无回退 → 放行
  └─ 有回退 → 标记对应 Case → 通知开发者 → 门禁阻断
```

### 6.7 自我评测修正闭环

#### 6.7.1 Evaluation Spec 规范（开发者定义）

```yaml
evaluation_spec:
  task_id: "data_analysis_001"
  max_retries: 3

  success_criteria:            # 结果层
    - id: SC1
      description: "输出包含完整的数据分析报告"
      check_type: llm_judge
      rubric: "报告包含以下章节：数据概览、趋势分析、异常检测、结论与建议"
      pass_threshold: 4       # 1-5 分，≥ 4 通过

  process_constraints:         # 过程层
    - id: PC1
      description: "必须先读取数据文件再进行任何分析操作"
      check_type: trace_analysis
      forbidden_pattern: "跳过 read_file 直接调用分析工具"

  efficiency_constraints:      # 效率层
    - id: EC1
      description: "端到端延迟不超过 60 秒"
      check_type: trace_analysis
      threshold:
        metric: total_duration_ms
        max: 60000

  safety_constraints:          # 风险层
    - id: SC1
      description: "不能写入系统目录"
      check_type: programmatic
      pattern: "^/(etc|bin|usr|System32)/"
      behavior: must_not_match
```

#### 6.7.2 修正策略映射

| 归因类型 | 自动修正策略 |
|---------|------------|
| 规划错误 | 调整 System Prompt 中的步骤顺序指令 |
| 工具调用错误 | 修正工具选择逻辑，补充参数描述 |
| Skill 缺陷 | 标记给开发者（无法自动修复 Skill 代码） |
| 环境异常 | 增加重试逻辑 + 超时配置 |
| 模型能力不足 | 标记"需人工介入" |

#### 6.7.3 防退化机制

每次修正后，**必须重新检验全部 Rubric**（包括之前已通过的），确保修复 A 没有破坏 B。若之前通过的 Rubric 在修复后变为未通过 → 回滚修改 → 标记"修正引入回退，需人工介入"。

### 6.8 Case 管理系统

#### 6.8.1 Case 生命周期

```
创建 (冷启动手工/ AI 辅助生成 / Bad Case 转化)
  → 草稿 (等待审核)
  → 已发布 (加入评测集)
  → 已归档 (场景过时/被更优 Case 替代)
```

#### 6.8.2 评测集分层

```
评测集金字塔:
        ┌──────┐
        │ 核心  │  50+ Case  (每次必跑，覆盖核心场景)
       ┌┴──────┴┐
       │ 扩展   │  200+ Case (每日跑，覆盖常见场景和边缘 Case)
      ┌┴────────┴┐
      │ 对抗     │  100+ Case (每次必跑，安全测试专用)
     ┌┴──────────┴┐
     │ 回归      │  500+ Case (每周跑，积累的全部历史 Case)
    └────────────┘
```

### 6.9 报告生成引擎

#### 6.9.1 报告输出规格

```json
{
  "report_id": "rpt_abc123",
  "submission_id": "sub_xyz789",
  "agent_name": "MyAgent",
  "agent_type": "long_horizon",
  "agent_version": "1.0.0",
  "created_at": "2026-08-08T12:00:00Z",
  "overall_score": 78.5,
  "grade": "B+",

  "dimensions": {
    "result": {
      "score": 82.0, "weight": 0.30,
      "sub_scores": {
        "task_success_rate": 85.0,
        "result_correctness": 80.0,
        "user_satisfaction": 81.0
      }
    },
    "trajectory": {
      "score": 75.0, "weight": 0.30,
      "sub_scores": {
        "plan_quality": 76.0,
        "tool_selection_accuracy": 78.0,
        "tool_call_correctness": 80.0,
        "error_recovery_rate": 70.0,
        "hallucination_rate": 5.0,
        "step_redundancy": 72.0
      }
    },
    "efficiency": {
      "score": 72.0, "weight": 0.20,
      "sub_scores": {
        "step_efficiency": 75.0,
        "token_efficiency": 68.0,
        "latency_p90_ms": 42000,
        "cost_per_task_usd": 0.085
      }
    },
    "security": {
      "score": 85.0, "weight": 0.20,
      "sub_scores": {
        "injection_resistance": 88.0,
        "jailbreak_resistance": 82.0,
        "dangerous_op_block_rate": 95.0,
        "over_refusal_rate": 8.0,
        "data_leak_rate": 2.0
      }
    }
  },

  "skill_evaluation": {
    "skills": [
      {
        "name": "data_analysis",
        "single_score": 88.0,
        "integration_score": 82.0,
        "status": "pass"
      }
    ]
  },

  "attribution": [
    {
      "type": "planning_error",
      "severity": "high",
      "frequency": 8,
      "finding": "Agent 在数据加载前就尝试进行分析操作",
      "suggestion": "在 System Prompt 中明确步骤顺序：先 read_file → 再 run_python"
    },
    {
      "type": "tool_call_error",
      "severity": "medium",
      "frequency": 5,
      "finding": "Agent 在 CSV 小于 100 行时仍调用 run_python（可用内置分析替代）",
      "suggestion": "增加工具选择逻辑：小数据集使用轻量方法，大数据集使用 Python"
    }
  ],

  "improvement_suggestions": [
    {
      "severity": "high",
      "dimension": "trajectory",
      "attribution_type": "planning_error",
      "finding": "...",
      "evidence": "8/30 测试用例出现此模式",
      "suggestion": "...",
      "affected_rubrics": ["R3", "R5"]
    }
  ],

  "self_evaluation_loop": {
    "enabled": true,
    "total_retries": 2,
    "initial_score": 68.0,
    "final_score": 78.5,
    "improvement": "+10.5",
    "retry_details": [...]
  },

  "radar_chart_data": {...},
  "benchmark_comparison": {
    "percentile": 72,
    "vs_baseline": "+12%",
    "vs_previous_version": null,
    "leaderboard_rank": 15
  }
}
```

---

## 7. 数据模型

### 7.1 核心实体 ER 图

```
┌──────────┐       ┌──────────────┐       ┌──────────────┐
│   User   │       │  Submission   │       │  Evaluation   │
│──────────│       │───────────────│       │───────────────│
│ id       │──┐    │ id            │──┐    │ id            │
│ username │  │    │ user_id (FK)  │  │    │ submission_id │
│ email    │  │    │ agent_name    │  │    │ status        │
│ api_key  │  └───►│ version       │  └───►│ agent_type    │
└──────────┘       │ config (JSONB)│       │ started_at    │
                   │ agent_type    │       │ completed_at  │
                   │ horizon       │       │ overall_score │
                   │ risk_level    │       │ grade         │
                   │ source_pkg    │       │ report_jsonb  │
                   └──────────────┘       └──────┬─────────┘
                                                 │
                 ┌────────────────────────────────┼──────────────────────────────┐
                 ▼                                ▼                              ▼
       ┌──────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
       │  TestResult  │    │     TraceData        │    │  SelfEvalLoopRun     │
       │──────────────│    │──────────────────────│    │──────────────────────│
       │ id           │    │ id                   │    │ id                   │
       │ eval_id (FK) │    │ eval_id (FK)         │    │ eval_id (FK)         │
       │ test_case_id │    │ trace_id             │    │ attempt_number       │
       │ dimension    │    │ root_span_id         │    │ score_before         │
       │ metric_name  │    │ total_spans          │    │ score_after          │
       │ score        │    │ total_duration_ms    │    │ attributions (JSONB) │
       │ max_score    │    │ total_tokens         │    │ corrections (JSONB)  │
       │ rubric_id    │    │ total_cost_usd       │    │ all_rubrics_passed   │
       │ details(JSONB│    │ storage_path         │    │ created_at           │
       └──────────────┘    └──────────────────────┘    └──────────────────────┘

       ┌──────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
       │  TestCase    │    │     SkillEval         │    │  QualityGate         │
       │──────────────│    │──────────────────────│    │──────────────────────│
       │ id           │    │ id                   │    │ id                   │
       │ task_id      │    │ submission_id (FK)   │    │ evaluation_id (FK)   │
       │ agent_type   │    │ skill_name           │    │ gate_type            │
       │ horizon      │    │ single_score         │    │ condition            │
       │ suite        │    │ integration_score    │    │ threshold            │
       │ prompt       │    │ status               │    │ actual_value         │
       │ context(JSONB│    │ details (JSONB)      │    │ passed               │
       │ rubric(JSONB)│    └──────────────────────┘    │ created_at           │
       │ tier         │                                └──────────────────────┘
       │ status       │
       └──────────────┘
```

### 7.2 核心 SQL 表

```sql
CREATE TABLE submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    agent_name VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL,
    agent_type VARCHAR(50) NOT NULL,        -- short_horizon | long_horizon
    horizon VARCHAR(10) NOT NULL,           -- short | long
    subtype VARCHAR(50),                    -- conversational | coding | rag | gui | workflow | custom
    risk_level VARCHAR(20) NOT NULL DEFAULT 'medium',
    config JSONB NOT NULL,
    source_package_path VARCHAR(500) NOT NULL,
    source_package_hash VARCHAR(64) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    status_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id UUID REFERENCES submissions(id),
    status VARCHAR(30) NOT NULL DEFAULT 'queued',
    agent_type VARCHAR(50) NOT NULL,
    horizon VARCHAR(10) NOT NULL,
    overall_score DECIMAL(5,2),
    grade VARCHAR(5),
    dimensions JSONB,                       -- 四层评测得分
    skill_evaluation JSONB,                 -- Skill 评测结果
    attribution JSONB,                      -- 归因分析
    improvement_suggestions JSONB,          -- 改进建议
    self_evaluation_loop JSONB,             -- 自评修正记录
    radar_chart_data JSONB,
    benchmark_comparison JSONB,
    report_full JSONB,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE test_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id UUID REFERENCES evaluations(id),
    test_case_id VARCHAR(100) NOT NULL,
    test_suite VARCHAR(50) NOT NULL,        -- core | extended | adversarial | regression
    dimension VARCHAR(50) NOT NULL,         -- result | trajectory | efficiency | security
    metric_name VARCHAR(100) NOT NULL,
    rubric_id VARCHAR(50),
    score DECIMAL(5,2),
    max_score DECIMAL(5,2),
    judge_type VARCHAR(30),                 -- programmatic | llm_judge | rule_engine | human
    judge_a_score DECIMAL(5,2),            -- Judge A 原始分
    judge_b_score DECIMAL(5,2),            -- Judge B 原始分
    judge_c_score DECIMAL(5,2),            -- Judge C 仲裁分 (如需要)
    agreement_level DECIMAL(3,2),          -- Judge 间一致度
    details JSONB,
    trace_storage_path VARCHAR(500),
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE test_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id VARCHAR(100) UNIQUE NOT NULL,
    agent_type VARCHAR(50) NOT NULL,
    horizon VARCHAR(10) NOT NULL,
    suite VARCHAR(50) NOT NULL,             -- core | extended | adversarial | regression
    tier VARCHAR(20) NOT NULL DEFAULT 'extended',
    prompt TEXT NOT NULL,
    context JSONB,                          -- files, skills, constraints, environment
    expected_behavior JSONB,                -- Expected Behavior 规范
    rubric JSONB NOT NULL,                  -- Rubric 列表
    source VARCHAR(50) DEFAULT 'manual',    -- manual | ai_generated | bad_case_conversion
    source_case_id VARCHAR(100),            -- Bad Case 转化来源
    status VARCHAR(20) DEFAULT 'draft',
    version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE trace_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id UUID REFERENCES evaluations(id),
    trace_id VARCHAR(64) NOT NULL,
    root_span_id VARCHAR(64) NOT NULL,
    total_spans INTEGER,
    total_duration_ms INTEGER,
    total_tokens INTEGER,
    total_cost_usd DECIMAL(10,6),
    error_spans INTEGER DEFAULT 0,
    storage_path VARCHAR(500) NOT NULL,
    spans_json_path VARCHAR(500),
    snapshots_json_path VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE skill_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id UUID REFERENCES evaluations(id),
    skill_name VARCHAR(255) NOT NULL,
    single_score DECIMAL(5,2),
    integration_score DECIMAL(5,2),
    single_pass BOOLEAN,
    integration_pass BOOLEAN,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE self_eval_loop_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id UUID REFERENCES evaluations(id),
    attempt_number INTEGER NOT NULL,
    score_before DECIMAL(5,2),
    score_after DECIMAL(5,2),
    attributions JSONB,
    corrections JSONB,
    all_rubrics_passed BOOLEAN,
    degraded BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE quality_gates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id UUID REFERENCES evaluations(id),
    gate_type VARCHAR(50) NOT NULL,         -- skill_launch | model_switch | prompt_change | ops_monitor
    condition VARCHAR(255) NOT NULL,
    threshold VARCHAR(50) NOT NULL,
    actual_value VARCHAR(50) NOT NULL,
    passed BOOLEAN NOT NULL,
    blocked BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_submissions_user ON submissions(user_id);
CREATE INDEX idx_submissions_status ON submissions(status);
CREATE INDEX idx_submissions_type ON submissions(agent_type, horizon);
CREATE INDEX idx_evaluations_submission ON evaluations(submission_id);
CREATE INDEX idx_evaluations_status ON evaluations(status);
CREATE INDEX idx_test_results_eval ON test_results(evaluation_id);
CREATE INDEX idx_test_results_dimension ON test_results(evaluation_id, dimension);
CREATE INDEX idx_test_cases_type ON test_cases(agent_type, horizon);
CREATE INDEX idx_test_cases_suite ON test_cases(suite);
CREATE INDEX idx_trace_metadata_eval ON trace_metadata(evaluation_id);
```

---

## 8. API 接口设计

### 8.1 RESTful API 总览

```
Base URL: https://api.agent-eval.example.com/v1
认证: Bearer Token (JWT)
```

### 8.2 接口列表

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/submissions` | 提交 Agent 源码包 |
| GET | `/v1/submissions/{id}/status` | 查询提交状态（含实时进度） |
| GET | `/v1/evaluations/{id}/report` | 获取评测报告 |
| GET | `/v1/evaluations/{id}/trace` | 获取全链路 Trace 数据（支持回放） |
| GET | `/v1/evaluations/{id}/trace/replay` | 交互式 Trace 回放 (SSE) |
| GET | `/v1/evaluations/{id}/self-eval-loops` | 获取自我评测修正循环详情 |
| GET | `/v1/leaderboard` | 排行榜 |
| GET | `/v1/test-cases` | 评测 Case 浏览 |
| POST | `/v1/test-cases` | 提交新 Case（Bad Case 转化） |
| GET | `/v1/quality-gates/{submission_id}` | 查询质量门禁状态 |

### 8.3 WebSocket 事件

```
wss://api.agent-eval.example.com/v1/ws/{submission_id}

事件:
  submission.validated       → { status, horizon }
  submission.failed          → { status, error }
  evaluation.stage_changed   → { stage, progress_pct }
  evaluation.progress        → { completed_tests, total_tests, current_dimension }
  evaluation.completed       → { evaluation_id, overall_score }
  evaluation.report_ready    → { report_url }
  self_eval_loop.iteration   → { attempt, score_before, score_after }
  quality_gate.result        → { gate_type, passed, blocked }
```

---

## 9. 安全设计

### 9.1 纵深防御体系

```
Layer 1 — 网络边界: API Gateway JWT + Rate Limiting + WAF + TLS 1.3
Layer 2 — 应用安全: Pydantic 强校验 + 文件病毒扫描 + 大小/类型限制
Layer 3 — 沙箱安全 (关键):
  ├─ 三级隔离: Docker / gVisor / Firecracker VM
  ├─ 静态代码扫描: Bandit + Safety
  ├─ 网络隔离: 仅白名单域名
  ├─ 资源硬限制: CPU/Mem/Disk/Process + 硬超时强制终止
  └─ 数据清理: 沙箱销毁后全量清理
Layer 4 — 数据安全:
  ├─ 静态加密: PostgreSQL TDE + MinIO SSE
  ├─ 传输加密: TLS 1.3
  ├─ 密钥管理: HashiCorp Vault
  └─ 审计日志: 不可变审计日志
```

### 9.2 三级安全矩阵

| | LOW RISK | MEDIUM RISK | HIGH RISK |
|------|---------|------------|----------|
| 沙箱 | Docker | Docker+gVisor | Firecracker VM |
| 文件系统 | 只读 | 受限读写 | 临时卷(销毁清) |
| 网络 | 仅API endpoint | 白名单域名 | 完全隔离 |
| 进程限制 | 20 | 50 | 100 |
| 系统调用 | 默认seccomp | 自定义seccomp | 严格白名单 |
| 权限提升 | 禁止 | 禁止 | 禁止 |

---

## 10. 部署架构

### 10.1 生产环境 (Kubernetes)

沙箱节点池独立部署（与业务服务物理隔离），其余服务与第 4 章技术栈选型一致。

### 10.2 开发环境

```bash
cd deploy/docker-compose && docker compose up -d
# 启动: API + Celery Worker + Frontend + PostgreSQL + Redis + MinIO + RabbitMQ + Jaeger + sandbox-dind
```

---

## 11. 落地路径与分阶段路线图

### 11.1 六步落地路径

| 步骤 | 内容 | 产出 | 周期 |
|------|------|------|------|
| Step 1 | **建观测**：搭建全链路 Trace 系统 | 每个 Agent 执行可回放 | 1-2 周 |
| Step 2 | **定指标**：定义分层评测指标 | 四层指标文档 + 目标值 | 3-5 天 |
| Step 3 | **建 Case**：构建种子评测集 | 冷启动 30+ 核心 Case | 1-2 周 |
| Step 4 | **跑对齐**：首次评测 + 标准对齐 (Dictator) | 人评一致率 ≥ 90% | 1-2 周 |
| Step 5 | **接 AI**：建立 LLM-as-Judge | 人机一致率 ≥ 85% | 1 周 |
| Step 6 | **转飞轮**：数据飞轮运转 | 持续迭代闭环 | 持续 |

### 11.2 分阶段交付路线图 (V1-V5)

| 阶段 | 能力 | 投入 | 产出价值 |
|------|------|------|---------|
| **V1** | 结果层程序化评测 | 1-2 周 | 自动检出明显任务失败 |
| **V2** | + 效率层评测 | +1 周 | 识别性能/成本问题 |
| **V3** | + 过程层 LLM-as-Judge | +1-2 周 | 识别路径/规划问题 |
| **V4** | + 风险层规则引擎 | +1 周 | 识别安全问题 |
| **V5** | + 自我评测修正闭环 | +2-3 周 | 自动修正 |

> 每个阶段独立交付价值——不需要等到 V5 才上线。

---

## 12. 附录

### 12.1 速查手册

| 概念 | 一句话 | 关键要点 |
|------|--------|---------|
| 评测四层 | 结果 / 过程 / 效率 / 风险 | 不能只看结果 |
| 分层指标 | 业务→任务→Agent→模型四层桥梁 | 不是堆指标，是搭桥 |
| 人人一致 | 评测员之间标准对齐 | 高方差比高偏差更危险 |
| 人机一致 | 机评和人评结果一致 | 低于 85% 不置信 |
| Rubric 二元化 | 模糊指标拆成是/否/未知 | 用 Unknown 反查合理性 |
| 数据飞轮 | 采集→清洗→评测→质检→归因→优化 | 起步先转起来 |
| Trajectory 评测 | 过程/轨迹评测 | 看 Agent 怎么做的 |
| Response 评测 | 结果评测 | 看 Agent 做成了什么 |
| Skill 评测 | 编写→发版→上线→监控全生命周期 | 强耦合执行环境，需沙箱化 |
| Task 三元组 | prompt - expected_behavior - transcript | 类比 query - ground_truth - answer |
| 自评修正闭环 | 执行→评测→归因→修正→重试 | 最大重试 + 防退化 |
| Bad Case | 失败样本价值远超通过样本 | 驱动评测集进化 |
| 七项基建能力 | 回放/Case/沙箱/AI Judge/归因/回归/门禁 | Agent 驾考系统 |
| 五类归因 | 规划/工具调用/Skill/环境/模型能力 | 精准定位失败环节 |
| 三级沙箱 | 只读/可写/高风险 | 按风险等级自动选 |

### 12.2 项目目录结构

```
AgentEvaluateSystem/
├── docs/SDD.md
├── backend/
│   ├── app/
│   │   ├── api/v1/             # REST API
│   │   ├── engine/             # 评测引擎
│   │   │   ├── result_eval.py       # 结果层评测
│   │   │   ├── trajectory_eval.py   # 过程层评测
│   │   │   ├── efficiency_eval.py   # 效率层评测
│   │   │   ├── security_eval.py     # 风险层评测
│   │   │   ├── skill_eval.py        # Skill 评测
│   │   │   ├── llm_judge.py         # AI Judge
│   │   │   ├── adversarial.py       # 对抗评测
│   │   │   ├── attribution.py       # 归因分析
│   │   │   ├── aggregator.py        # 评分聚合
│   │   │   └── self_eval_loop.py    # 自评修正
│   │   ├── infrastructure/     # 基建层
│   │   │   ├── replay.py            # 全链路回放
│   │   │   ├── case_manager.py      # Case 管理
│   │   │   ├── regression.py        # 回归引擎
│   │   │   └── quality_gate.py      # 准入准出门禁
│   │   ├── services/           # 业务服务
│   │   ├── models/             # ORM
│   │   ├── schemas/            # Pydantic
│   │   └── worker/             # Celery 任务
│   └── tests/
├── frontend/
│   └── src/
│       ├── pages/              # Dashboard / Report / TraceViewer
│       └── components/         # RadarChart / ScoreCard / ReplayPlayer
├── sandbox/                    # 沙箱镜像 + Agent Runner
│   ├── Dockerfile.readonly
│   ├── Dockerfile.writable
│   └── Dockerfile.highrisk
├── deploy/
│   ├── kubernetes/
│   └── docker-compose/
└── .github/workflows/
```

### 12.3 错误处理策略

| 场景 | 处理方式 |
|------|---------|
| 沙箱构建失败 | BUILD_ERROR + pip install 日志 |
| Agent 超时 | 强制终止，已完成评测保留 |
| Agent 崩溃 | 保留崩溃前 Trace，标注 CRASHED，部分评分 |
| LLM-as-Judge API 异常 | 重试 3 次 → 降级为纯规则评分 |
| 对抗攻击导致沙箱异常 | 立即隔离，安全审查，不返回详细 Trace |
| 人机一致率 < 85% | 暂停自动评测，人工校准后恢复 |
| 回归检出回退 | 门禁阻断，通知相关人员 |
| 自评修正超过最大重试 | 返回最优结果 + "需人工介入"标记 |
