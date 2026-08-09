from __future__ import annotations

from enum import Enum
from typing import Any


class SubmissionStatus(str, Enum):
    DRAFT = "draft"
    VALIDATING = "validating"
    VALIDATION_FAILED = "validation_failed"
    BUILD_QUEUED = "build_queued"
    BUILDING = "building"
    BUILD_FAILED = "build_failed"
    IMAGE_SCANNING = "image_scanning"
    IMAGE_REJECTED = "image_rejected"
    IMAGE_READY = "image_ready"


class CaseSetStatus(str, Enum):
    PENDING = "pending"
    COUNCIL_REVIEWING = "council_reviewing"
    VALIDATION_FAILED = "validation_failed"
    NEEDS_REVIEW = "needs_review"
    READY = "ready"


class EvaluationStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    CANCELLED = "cancelled"


SUBMISSION_TRANSITIONS = {
    SubmissionStatus.BUILD_QUEUED: {SubmissionStatus.BUILDING, SubmissionStatus.BUILD_FAILED},
    SubmissionStatus.BUILDING: {SubmissionStatus.IMAGE_SCANNING, SubmissionStatus.BUILD_FAILED},
    SubmissionStatus.IMAGE_SCANNING: {SubmissionStatus.IMAGE_READY, SubmissionStatus.IMAGE_REJECTED, SubmissionStatus.BUILD_FAILED},
}
CASE_SET_TRANSITIONS = {
    CaseSetStatus.PENDING: {CaseSetStatus.COUNCIL_REVIEWING, CaseSetStatus.VALIDATION_FAILED},
    CaseSetStatus.COUNCIL_REVIEWING: {CaseSetStatus.READY, CaseSetStatus.NEEDS_REVIEW, CaseSetStatus.VALIDATION_FAILED},
}
EVALUATION_TRANSITIONS = {
    EvaluationStatus.QUEUED: {EvaluationStatus.RUNNING, EvaluationStatus.FAILED, EvaluationStatus.CANCELLED},
    EvaluationStatus.RUNNING: {EvaluationStatus.AGGREGATING, EvaluationStatus.FAILED, EvaluationStatus.CANCELLED},
    EvaluationStatus.AGGREGATING: {EvaluationStatus.COMPLETED, EvaluationStatus.NEEDS_REVIEW, EvaluationStatus.FAILED},
}


def transition(entity: Any, target: Enum, transitions: dict[Enum, set[Enum]]) -> None:
    enum_type = type(target)
    try:
        current = enum_type(entity.status)
    except ValueError as exc:
        raise ValueError(f"未知状态: {entity.status}") from exc
    if target not in transitions.get(current, set()):
        raise ValueError(f"非法状态迁移: {current.value} -> {target.value}")
    entity.status = target.value
