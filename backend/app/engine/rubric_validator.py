from __future__ import annotations

import re

from app.core.exceptions import ValidationException
from app.schemas.internal.rubric import Rubric


AMBIGUOUS_TERMS = ("比较好", "基本可以", "差不多", "尽量", "适当", "较为")


class RubricValidator:
    def validate(self, rubrics: list[Rubric]) -> list[Rubric]:
        ids: set[str] = set()
        for rubric in rubrics:
            if rubric.id in ids:
                raise ValidationException(f"Rubric ID 重复: {rubric.id}")
            ids.add(rubric.id)
            if any(term in rubric.pass_condition for term in AMBIGUOUS_TERMS):
                raise ValidationException(f"Rubric 通过条件含模糊表述: {rubric.id}")
            if rubric.check_type.value == "programmatic" and not re.search(
                r"(不|零|=|≥|≤|大于|小于|低于|超过|通过|一致|全部|均|完整|成功|包含|100%|率)",
                rubric.pass_condition,
            ):
                raise ValidationException(f"程序化 Rubric 缺少可判定条件: {rubric.id}")
        return rubrics

    def deduplicate(self, rubrics: list[Rubric]) -> list[Rubric]:
        seen: set[tuple[str, str]] = set()
        result = []
        for rubric in rubrics:
            normalized = re.sub(r"\W+", "", rubric.description).lower()
            key = (rubric.dimension.value, normalized)
            if key not in seen:
                seen.add(key)
                result.append(rubric)
        return result
