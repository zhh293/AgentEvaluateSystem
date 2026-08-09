"""Application service for the bounded self-evaluation correction loop."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.engine.self_eval_loop import SelfEvalLoop


class SelfEvaluationService:
    async def run(
        self,
        config: dict,
        evaluate: Callable[[dict], Any],
        attribute: Callable[[dict], list],
        max_retries: int = 3,
    ) -> dict:
        return await SelfEvalLoop(max_retries=max_retries).run(config, evaluate, attribute)


self_eval_service = SelfEvaluationService()
