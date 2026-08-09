import importlib.util
import json
from pathlib import Path


def _load_recorder_class():
    path = Path(__file__).parents[2] / "sandbox" / "otel_instrument.py"
    spec = importlib.util.spec_from_file_location("sandbox_otel", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.TraceRecorder


def test_trace_hierarchy_and_secret_redaction():
    recorder = _load_recorder_class()()
    with recorder.span("AGENT_EXECUTION", {"api_key": "secret"}) as root:
        with recorder.span("TOOL_EXECUTION", {"tool.name": "search"}):
            pass

    payload = json.loads(recorder.to_json())
    by_type = {span["span_type"]: span for span in payload["spans"]}
    assert by_type["AGENT_EXECUTION"]["attributes"]["api_key"] == "[REDACTED]"
    assert by_type["TOOL_EXECUTION"]["parent_span_id"] == root
