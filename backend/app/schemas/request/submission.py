from pydantic import BaseModel, Field


class SubmissionConfigRequest(BaseModel):
    """前端表单提交的 Agent 配置数据"""

    # 基础信息
    agent_name: str = Field(min_length=1, max_length=255)
    version: str = Field(default="1.0.0")

    # 核心必填：Agent 功能描述（至少 30 字）
    description: str = Field(min_length=30)

    # 模型配置
    llm_provider: str
    llm_model: str
    llm_api_base: str
    llm_api_key: str
    llm_max_output_tokens: int = 4096
    llm_temperature: float = 0.7

    # Agent 类型（可选，留空则 AI 自动识别）
    agent_type: str | None = None
    subtype: str | None = None

    # 工具勾选
    enabled_tools: list[str] = Field(default_factory=list)

    # 自定义工具
    custom_tools: list[dict] = Field(default_factory=list)

    # Skill 配置（长程 Agent 专有）
    skills: list[dict] = Field(default_factory=list)

    # 约束条件
    language: str = "简体中文"
    max_output_chars: int | None = None
    output_format: str = "markdown"
    tone: str = ""
    require_bullet_points: bool = False
    max_steps: int = 20
    max_execution_time_seconds: int = 300

    # 自评闭环
    self_eval_enabled: bool = False
    self_eval_max_retries: int = 3

    # 高级设置
    expected_input_type: str = "text"
    expected_output_type: str = "text"
    allowed_domains: list[str] = Field(default_factory=list)
    dockerfile_path: str | None = None
