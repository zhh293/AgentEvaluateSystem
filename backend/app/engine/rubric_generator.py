from __future__ import annotations

from app.engine.rubric_builtin import ALL_BUILTIN_RUBRICS
from app.engine.rubric_case_parser import CaseRubricParser
from app.engine.rubric_templates import derive_config_rubrics
from app.engine.rubric_validator import RubricValidator
from app.schemas.internal.rubric import Rubric


class RubricGenerator:
    def __init__(self) -> None:
        self.validator = RubricValidator()

    def _layer1_builtin(self) -> list[Rubric]:
        return [rubric.model_copy(deep=True) for rubric in ALL_BUILTIN_RUBRICS]

    def _layer2_config_derived(self, agent_config) -> list[Rubric]:
        return derive_config_rubrics(agent_config)

    def _layer4_case_parse(self, test_cases: list[dict]) -> list[Rubric]:
        parser = CaseRubricParser()
        result = []
        for case_file in test_cases:
            result.extend(parser.parse_and_generate(case_file["content"], case_file["format"]))
        return result

    def generate_all_rubrics(
        self,
        agent_config,
        task_description: str | None = None,
        test_cases: list[dict] | None = None,
        ai_rubrics: list[Rubric] | None = None,
    ) -> list[Rubric]:
        rubrics = self._layer1_builtin() + self._layer2_config_derived(agent_config)
        # AI generation is asynchronous and supplied by AIRubricGenerator after
        # Phase 7; accepting results here keeps the main merge pipeline pure.
        if task_description and ai_rubrics:
            rubrics.extend(ai_rubrics)
        if test_cases:
            rubrics.extend(self._layer4_case_parse(test_cases))
        rubrics = self.validator.deduplicate(rubrics)
        # Sources may share stable IDs (e.g. multiple case files). Re-number
        # duplicates after semantic deduplication without changing the source.
        used: dict[str, int] = {}
        for rubric in rubrics:
            count = used.get(rubric.id, 0)
            used[rubric.id] = count + 1
            if count:
                rubric.id = f"{rubric.id}-{count + 1}"
        return self.validator.validate(rubrics)
