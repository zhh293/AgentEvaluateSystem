from __future__ import annotations

import json
import re

from app.engine.llm_judge import JudgeTransport, _parse_json
from app.engine.rubric_validator import RubricValidator
from app.schemas.internal.rubric import Rubric, RubricSource


RUBRIC_GENERATION_PROMPT = """你是 Agent 评测标准设计专家。
Agent 类型：{agent_type}；子类型：{subtype}；工具：{tools}
任务描述：{task_description}
合格标准：{quality_requirements}
生成 8-15 条互不重复 Rubric，覆盖 result、trajectory、security。
每条必须有明确可判定 pass_condition；verdict_type 只能 binary/ternary；check_type 只能 programmatic/llm_judge/rule_engine。
不要重复通用的语法、PII、危险系统调用检查。
只输出 JSON：{{"rubrics":[{{"description":"...","dimension":"result","check_type":"llm_judge","verdict_type":"binary","pass_condition":"...","weight":1.0}}]}}
"""


class AIRubricGenerator:
    def __init__(self, transport: JudgeTransport):
        self.transport = transport
        self.validator = RubricValidator()

    async def generate_from_description(self, task_description: str, quality_requirements: str = "", agent_config=None) -> list[Rubric]:
        tools = getattr(agent_config, "enabled_tools", []) if agent_config else []
        prompt = RUBRIC_GENERATION_PROMPT.format(
            agent_type=getattr(agent_config, "agent_type", "unknown"),
            subtype=getattr(agent_config, "subtype", "unknown"),
            tools=", ".join(map(str, tools)) or "无",
            task_description=task_description,
            quality_requirements=quality_requirements or "未提供",
        )
        payload = _parse_json(await self.transport.complete(prompt))
        raw = payload.get("rubrics", [])
        if not 8 <= len(raw) <= 15:
            raise ValueError("AI 生成 Rubric 数量必须为 8-15 条")
        rubrics = []
        for index, item in enumerate(raw, 1):
            item = dict(item)
            item.update({"id": f"AI-GEN-{index:03d}", "source": RubricSource.AI_GENERATED})
            rubrics.append(Rubric.model_validate(item))
        return self.validator.validate(self.validator.deduplicate(rubrics))
