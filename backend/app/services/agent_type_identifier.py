import json
import logging
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)

AGENT_TYPE_IDENTIFICATION_PROMPT = """你是一个 Agent 架构分析专家。请根据以下 Agent 描述，判断其时间视野类型和业务子类型。

## Agent 描述
{description}

## 判断标准

### 时间视野类型（二选一）
- short_horizon：任务目标明确单一，执行步骤 1-5 步，无多阶段规划需求
  典型场景：客服问答、AI 搜索、单轮对话、内容摘要、翻译
- long_horizon：任务目标复杂模糊，需要多步规划（10+ 步）、工具编排、状态管理
  典型场景：编程助手、数据分析流水线、运维自动化、多功能办公 Agent

### 业务子类型（六选一）
- conversational：对话/客服/问答类
- coding：代码生成/编程助手类
- rag：检索增强生成类
- gui：GUI 操作/计算机使用类
- workflow：工作流/流水线编排类
- custom：无法归类或用户自定义

## 输出格式
以 JSON 返回，不要带额外说明：
{{"agent_type": "short_horizon|long_horizon", "subtype": "conversational|coding|rag|gui|workflow|custom", "confidence": 0.0-1.0, "reasoning": "简短判断理由"}}
"""


@dataclass
class TypeIdentificationResult:
    agent_type: str  # short_horizon / long_horizon
    subtype: str     # conversational / coding / rag / gui / workflow / custom
    confidence: float
    reasoning: str = ""


class AgentTypeIdentifier:
    """基于 Agent 描述自动识别时间视野类型和业务子类型"""

    async def identify(self, description: str) -> TypeIdentificationResult:
        import httpx

        prompt = AGENT_TYPE_IDENTIFICATION_PROMPT.format(description=description)

        url = settings.JUDGE_API_BASE.rstrip("/") + "/chat/completions"
        async with httpx.AsyncClient(timeout=httpx.Timeout(30)) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.JUDGE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.JUDGE_MODEL_A,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 200,
                },
            )

        if response.status_code != 200:
            logger.warning(f"AI 类型识别调用失败: {response.status_code}")
            return TypeIdentificationResult(
                agent_type="short_horizon", subtype="custom", confidence=0.0,
                reasoning=f"识别服务暂时不可用（{response.status_code}），使用默认类型"
            )

        raw = response.json()["choices"][0]["message"]["content"].strip()
        return self._parse_response(raw)

    def _parse_response(self, raw: str) -> TypeIdentificationResult:
        try:
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                if raw.endswith("```"):
                    raw = raw.rsplit("\n", 1)[0]
            data = json.loads(raw)
            return TypeIdentificationResult(
                agent_type=data.get("agent_type", "short_horizon"),
                subtype=data.get("subtype", "custom"),
                confidence=float(data.get("confidence", 0.0)),
                reasoning=data.get("reasoning", ""),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"AI 类型识别结果解析失败: {e}, raw={raw[:200]}")
            return TypeIdentificationResult(
                agent_type="short_horizon", subtype="custom", confidence=0.0,
                reasoning="识别结果解析失败，使用默认类型"
            )


agent_type_identifier = AgentTypeIdentifier()
