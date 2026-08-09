import csv
import io
import json

from app.core.exceptions import ValidationException
from app.schemas.internal.rubric import Rubric, RubricCheckType, RubricDimension, RubricSource


class CaseRubricParser:
    SUPPORTED_FORMATS = {"csv", "json", "jsonl"}
    QUESTION_KEYS = {"question", "query", "prompt", "input", "问题", "提问"}
    ANSWER_KEYS = {"answer", "ground_truth", "expected", "reference", "参考答案", "正确答案"}

    def parse_records(self, content: str, file_format: str) -> list[dict]:
        file_format = file_format.lower().lstrip(".")
        if file_format not in self.SUPPORTED_FORMATS:
            raise ValidationException(f"不支持的测试集格式: {file_format}")
        if not content.strip():
            return []
        try:
            if file_format == "csv":
                records = list(csv.DictReader(io.StringIO(content)))
            elif file_format == "jsonl":
                records = [json.loads(line) for line in content.splitlines() if line.strip()]
            else:
                payload = json.loads(content)
                records = payload if isinstance(payload, list) else payload.get("cases", [])
        except (json.JSONDecodeError, csv.Error, AttributeError) as exc:
            raise ValidationException(f"测试集解析失败: {exc}") from exc
        if not all(isinstance(record, dict) for record in records):
            raise ValidationException("测试集记录必须是对象")
        return records

    def parse_and_generate(self, content: str, file_format: str) -> list[Rubric]:
        records = self.parse_records(content, file_format)
        if not records:
            return []
        keys = {str(key).lower() for record in records for key in record}
        if not keys.intersection(self.QUESTION_KEYS):
            raise ValidationException("测试集未找到 question/query/input 字段")
        has_answers = bool(keys.intersection(self.ANSWER_KEYS))
        definitions = (
            [
                ("CASE-ACC-001", "答案与参考答案语义一致", "语义相似度不低于 0.85", "programmatic"),
                ("CASE-ACC-002", "输出覆盖参考答案中的关键实体", "关键实体召回率不低于 80%", "programmatic"),
            ]
            if has_answers
            else [
                ("CASE-CMP-001", "所有测试问题均获得有效非空回答", "有效回答率不低于 90%", "programmatic"),
                ("CASE-CMP-002", "回答内容与测试问题直接相关", "Judge 判定有效回答率不低于 85%", "llm_judge"),
            ]
        )
        return [
            Rubric(
                id=identifier,
                description=description,
                dimension=RubricDimension.RESULT,
                check_type=RubricCheckType(check),
                source=RubricSource.CASE_PARSED,
                pass_condition=condition,
                metadata={"case_count": len(records)},
            )
            for identifier, description, condition, check in definitions
        ]
