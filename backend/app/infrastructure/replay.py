from __future__ import annotations

from copy import deepcopy


class TraceReplayEngine:
    def __init__(self, trace_data: dict):
        self.spans = sorted(trace_data.get("spans", []), key=lambda span: span.get("started_ns", span.get("timestamp_ms", 0)))
        self.snapshots = sorted(trace_data.get("environment_snapshots", []), key=lambda item: item.get("timestamp_ms", 0))
        self.current_index = -1

    def step_forward(self):
        if self.current_index + 1 >= len(self.spans):
            return None
        self.current_index += 1
        return self.spans[self.current_index]

    def step_backward(self):
        if self.current_index - 1 < 0:
            self.current_index = -1
            return None
        self.current_index -= 1
        return self.spans[self.current_index]

    def jump_to(self, span_id: str):
        for index, span in enumerate(self.spans):
            if span.get("span_id") == span_id:
                self.current_index = index
                return span
        raise KeyError(f"span not found: {span_id}")

    def filter_by_type(self, span_type: str) -> list[dict]:
        return [span for span in self.spans if span.get("span_type") == span_type]

    def get_snapshot_at(self, timestamp_ms: int) -> dict:
        candidates = [item for item in self.snapshots if item.get("timestamp_ms", 0) <= timestamp_ms]
        return deepcopy(candidates[-1]) if candidates else {}

    def compare_snapshots(self, ts1: int, ts2: int) -> dict:
        before, after = self.get_snapshot_at(ts1).get("state", {}), self.get_snapshot_at(ts2).get("state", {})
        keys = set(before) | set(after)
        return {"added": {key: after[key] for key in keys - set(before)}, "removed": {key: before[key] for key in keys - set(after)}, "changed": {key: {"before": before[key], "after": after[key]} for key in keys & set(before) & set(after) if before[key] != after[key]}}
