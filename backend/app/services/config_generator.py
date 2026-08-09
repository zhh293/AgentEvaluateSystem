import io
import logging
from app.engine.builtin_tools import match_enabled_tools

logger = logging.getLogger(__name__)

LLM_PROVIDER_PRESETS: dict[str, str | None] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "deepseek": "https://api.deepseek.com",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "moonshot": "https://api.moonshot.cn/v1",
    "custom": None,
}


class ConfigGenerator:
    """将前端表单数据转为标准 agent.config.yaml"""

    def generate(self, form_data) -> str:
        import yaml

        agent_type = form_data.agent_type or "short_horizon"
        subtype = form_data.subtype or "custom"
        horizon = "short" if agent_type != "long_horizon" else "long"

        config = {
            "agent": {
                "name": form_data.agent_name,
                "version": form_data.version,
                "type": agent_type,
                "subtype": subtype,
                "description": form_data.description,
                "horizon": horizon,
                "llm": {
                    "provider": form_data.llm_provider,
                    "model": form_data.llm_model,
                    "requires_api_key": True,
                    "api_base": form_data.llm_api_base or LLM_PROVIDER_PRESETS.get(form_data.llm_provider),
                    "temperature": form_data.llm_temperature,
                    "max_output_tokens": form_data.llm_max_output_tokens,
                },
                "tools": self._build_tools_section(form_data.enabled_tools, form_data.custom_tools),
                "skills": form_data.skills,
                "expected_input": {"type": form_data.expected_input_type},
                "expected_output": {"type": form_data.expected_output_type},
                "constraints": self._build_constraints(form_data),
                "self_evaluation": {
                    "enabled": form_data.self_eval_enabled,
                    "max_retries": form_data.self_eval_max_retries,
                },
            }
        }
        return yaml.dump(config, allow_unicode=True, default_flow_style=False)

    def _build_tools_section(self, enabled_tool_ids: list[str], custom_tools: list[dict]) -> list[dict]:
        tools: list[dict] = []
        matched = match_enabled_tools(enabled_tool_ids)
        for tool in matched:
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "risk_level": tool.risk_level,
                "category": tool.category,
            })
        for ct in custom_tools:
            tools.append({
                "name": ct.get("name", "custom_tool"),
                "description": ct.get("description", ""),
                "risk_level": ct.get("risk_level", "medium"),
                "category": "自定义工具",
                "params": ct.get("params", {}),
            })
        return tools

    def _build_constraints(self, form_data) -> dict:
        constraints = {
            "language": form_data.language,
            "output_format": form_data.output_format,
            "max_steps": form_data.max_steps,
            "max_execution_time_seconds": form_data.max_execution_time_seconds,
        }
        if form_data.max_output_chars is not None:
            constraints["max_output_chars"] = form_data.max_output_chars
        if form_data.tone:
            constraints["tone"] = form_data.tone
        if form_data.require_bullet_points:
            constraints["require_bullet_points"] = True
        if form_data.allowed_domains:
            constraints["allowed_domains"] = form_data.allowed_domains
        return constraints


config_generator = ConfigGenerator()
