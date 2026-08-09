"""Provider-neutral LLM-as-Judge with strict evidence validation."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field, field_validator

from app.schemas.internal.rubric import RubricVerdict
from app.schemas.internal.trace import SpanData


JUDGE_PROMPT_TEMPLATE = """你是 Agent 评测专家。仅根据给定 Rubric 和执行片段评分。

Rubric: {rubric_description}
通过条件: {pass_condition}

相关执行片段:
{trajectory_context}

要求：
1. verdict 只能是 Yes、No、Unknown。
2. score 为 1-5；Unknown 时仍按证据充分程度评分，但必须解释原因。
3. evidence 必须引用上方真实 Span ID；没有证据时使用空数组，禁止编造。
4. 只输出 JSON：{{"verdict":"Yes|No|Unknown","score":1,"reasoning":"...","evidence":[{{"span_id":"...","quote":"..."}}]}}
"""


class Evidence(BaseModel):
    span_id: str
    quote: str = ""


class JudgeResult(BaseModel):
    verdict: RubricVerdict
    score: int = Field(ge=1, le=5)
    reasoning: str = Field(min_length=2)
    evidence: list[Evidence] = Field(default_factory=list)
    model: str = ""


class DualJudgeResult(BaseModel):
    rubric_id: str = ""
    final_score: float | None
    final_verdict: RubricVerdict | None
    judge_a: JudgeResult
    judge_b: JudgeResult
    judge_c: JudgeResult | None = None
    agreement_level: float
    arbitrated: bool = False
    needs_human_review: bool = False


class JudgeTransport(Protocol):
    async def complete(self, prompt: str) -> str: ...


class HTTPJudgeTransport:
    def __init__(self, model: str, api_key: str, api_base: str, provider: str = "openai", timeout: int = 60):
        self.model, self.api_key, self.api_base, self.provider, self.timeout = model, api_key, api_base.rstrip("/"), provider, timeout

    async def complete(self, prompt: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self.provider == "anthropic":
            headers.update({"x-api-key": self.api_key, "anthropic-version": "2023-06-01"})
            url = self.api_base + "/messages"
            body = {"model": self.model, "max_tokens": 800, "temperature": 0, "messages": [{"role": "user", "content": prompt}]}
        else:
            headers["Authorization"] = f"Bearer {self.api_key}"
            url = self.api_base + "/chat/completions"
            body = {"model": self.model, "temperature": 0, "max_tokens": 800, "response_format": {"type": "json_object"}, "messages": [{"role": "user", "content": prompt}]}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
        if self.provider == "anthropic":
            return "".join(block.get("text", "") for block in payload.get("content", []))
        return payload["choices"][0]["message"]["content"]


def _span_payload(span: SpanData) -> dict:
    return {
        "span_id": span.span_id,
        "type": span.span_type.value,
        "operation": span.operation,
        "status": span.status,
        "input": span.input,
        "output": span.output,
        "attributes": {key: value for key, value in span.attributes.items() if not any(marker in key.lower() for marker in ("key", "secret", "token", "password", "authorization"))},
        "error": span.error,
    }


def _parse_json(raw: str) -> dict:
    value = raw.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.I)
    return json.loads(value)


class AIJudge:
    def __init__(self, model: str, api_key: str = "", api_base: str = "https://api.openai.com/v1", provider: str = "openai", transport: JudgeTransport | None = None):
        self.model = model
        self.transport = transport or HTTPJudgeTransport(model, api_key, api_base, provider)

    async def judge_rubric(self, rubric: dict, trajectory_context: list[SpanData]) -> JudgeResult:
        context = json.dumps([_span_payload(span) for span in trajectory_context], ensure_ascii=False, default=str)
        prompt = JUDGE_PROMPT_TEMPLATE.format(
            rubric_description=rubric.get("description", ""),
            pass_condition=rubric.get("pass_condition", ""),
            trajectory_context=context,
        )
        result = JudgeResult.model_validate(_parse_json(await self.transport.complete(prompt)))
        valid_ids = {span.span_id for span in trajectory_context}
        invented = [item.span_id for item in result.evidence if item.span_id not in valid_ids]
        if invented:
            raise ValueError(f"Judge 引用了不存在的 Span: {invented}")
        result.model = self.model
        return result


def _verdict(results: list[JudgeResult]) -> RubricVerdict:
    counts = {value: sum(result.verdict == value for result in results) for value in RubricVerdict}
    return max(counts, key=counts.get)


async def dual_judge_rubric(rubric: dict, trajectory_context: list[SpanData], judge_a: AIJudge, judge_b: AIJudge, judge_c: AIJudge | None = None) -> DualJudgeResult:
    result_a, result_b = await asyncio.gather(
        judge_a.judge_rubric(rubric, trajectory_context),
        judge_b.judge_rubric(rubric, trajectory_context),
    )
    deviation = abs(result_a.score - result_b.score)
    agreement = max(0.0, 1.0 - deviation / 4.0)
    if deviation <= 1 and result_a.verdict == result_b.verdict:
        return DualJudgeResult(rubric_id=str(rubric.get("id", "")), final_score=round((result_a.score + result_b.score) / 2, 1), final_verdict=result_a.verdict, judge_a=result_a, judge_b=result_b, agreement_level=agreement)
    if deviation <= 2 and judge_c is not None:
        result_c = await judge_c.judge_rubric(rubric, trajectory_context)
        return DualJudgeResult(rubric_id=str(rubric.get("id", "")), final_score=float(result_c.score), final_verdict=result_c.verdict, judge_a=result_a, judge_b=result_b, judge_c=result_c, agreement_level=agreement, arbitrated=True)
    return DualJudgeResult(rubric_id=str(rubric.get("id", "")), final_score=None, final_verdict=None, judge_a=result_a, judge_b=result_b, agreement_level=agreement, needs_human_review=True)
