import json
import logging
from dataclasses import dataclass, field
from app.services.config_generator import LLM_PROVIDER_PRESETS

logger = logging.getLogger(__name__)


@dataclass
class ConnectivityResult:
    ok: bool
    model: str = ""
    error: str = ""
    latency_ms: float = 0.0


class ModelConnectivityChecker:
    """提交时自动发起测试调用，验证 API 地址与密钥有效性"""

    async def check(
        self,
        provider: str,
        api_base: str,
        api_key: str,
        model: str,
        timeout: int = 15,
    ) -> ConnectivityResult:
        import time
        import httpx

        base_url = api_base or LLM_PROVIDER_PRESETS.get(provider, "")
        if not base_url:
            return ConnectivityResult(ok=False, error=f"无法确定 {provider} 的 API 地址")

        headers = {"Content-Type": "application/json"}
        if provider.lower() == "anthropic":
            url = base_url.rstrip("/") + "/messages"
            headers.update({"x-api-key": api_key, "anthropic-version": "2023-06-01"})
            body = {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}
        else:
            url = base_url.rstrip("/") + "/chat/completions"
            headers["Authorization"] = f"Bearer {api_key}"
            body = {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
                response = await client.post(url, headers=headers, json=body)
                latency_ms = (time.perf_counter() - start) * 1000

            if response.status_code == 200:
                logger.info(f"模型连通性校验通过: {provider}/{model} ({latency_ms:.0f}ms)")
                return ConnectivityResult(ok=True, model=model, latency_ms=latency_ms)

            if response.status_code in (401, 403):
                return ConnectivityResult(
                    ok=False, model=model, error="认证失败：检查 API Key 是否有效"
                )
            if response.status_code == 404:
                return ConnectivityResult(
                    ok=False, model=model, error=f"模型 {model} 在 {provider} 上不存在"
                )
            detail = _extract_error(response)
            return ConnectivityResult(
                ok=False, model=model, error=f"API 返回异常 ({response.status_code}): {detail}"
            )

        except httpx.TimeoutException:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectivityResult(
                ok=False, model=model, error=f"连接超时（{timeout}s），检查 API 地址或网络", latency_ms=elapsed
            )
        except httpx.ConnectError:
            return ConnectivityResult(
                ok=False, model=model, error=f"无法连接到 API 地址: {base_url}"
            )
        except Exception as e:
            return ConnectivityResult(
                ok=False, model=model, error=f"连通性检测异常: {e}"
            )


def _extract_error(response) -> str:
    try:
        body = response.json()
        if "error" in body:
            err = body["error"]
            if isinstance(err, dict):
                return err.get("message", str(err))
            return str(err)
        return response.text[:200]
    except Exception:
        return response.text[:200]


connectivity_checker = ModelConnectivityChecker()
