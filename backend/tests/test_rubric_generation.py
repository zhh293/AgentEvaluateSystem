import pytest

from app.engine.rubric_case_parser import CaseRubricParser
from app.engine.rubric_generator import RubricGenerator
from app.engine.rubric_templates import RubricTemplateLibrary
from app.schemas.request.submission import SubmissionConfigRequest


def config(**overrides):
    values = dict(
        agent_name="rubric-agent",
        description="A detailed RAG agent used to verify rubric generation behavior.",
        llm_provider="openai",
        llm_model="test",
        llm_api_base="https://example.invalid/v1",
        llm_api_key="secret",
        subtype="rag",
        enabled_tools=["search_knowledge_base"],
        language="中文",
        max_output_chars=500,
        require_bullet_points=True,
    )
    values.update(overrides)
    return SubmissionConfigRequest(**values)


def test_builtin_library_is_complete_and_binary():
    rubrics = RubricGenerator()._layer1_builtin()
    assert len(rubrics) >= 29
    assert {item.dimension.value for item in rubrics} == {
        "result", "trajectory", "efficiency", "security"
    }
    assert all(item.verdict_type in {"binary", "ternary"} for item in rubrics)


def test_rag_and_constraints_generate_specific_rubrics():
    rubrics = RubricGenerator()._layer2_config_derived(config())
    descriptions = "\n".join(item.description for item in rubrics)
    assert "引用" in descriptions
    assert "幻觉" in descriptions
    assert "500" in descriptions
    assert "分点" in descriptions


@pytest.mark.parametrize(
    ("content", "format", "expected_prefix"),
    [
        ('question,ground_truth\n"2+2","4"', "csv", "CASE-ACC"),
        ('{"question":"hello"}\n', "jsonl", "CASE-CMP"),
        ('[{"input":"hello","expected":"world"}]', "json", "CASE-ACC"),
    ],
)
def test_case_parser_formats(content, format, expected_prefix):
    rubrics = CaseRubricParser().parse_and_generate(content, format)
    assert len(rubrics) == 2
    assert all(item.id.startswith(expected_prefix) for item in rubrics)


def test_full_generation_deduplicates_and_validates():
    rubrics = RubricGenerator().generate_all_rubrics(
        config(), test_cases=[{"content": '[{"question":"x"}]', "format": "json"}]
    )
    assert len({item.id for item in rubrics}) == len(rubrics)


def test_template_library_loads_four_scenarios_and_matches_subtype():
    library = RubricTemplateLibrary()
    assert len(library.templates) >= 4
    matched = library.match_templates({"subtype": "rag"}, "知识库检索和引用")
    assert len(matched) >= 2
    assert all(item.id.startswith("TPL-RAG") for item in matched)
    assert library.match_templates({"subtype": "unknown"}, "unknown") == []
