import json

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_db
from app.infrastructure.minio import minio_client
from app.models.submission import Submission
from app.schemas.request.submission import SubmissionConfigRequest
from app.schemas.response.submission import SubmissionResponse, SubmissionStatusResponse, ToolInfo
from app.services.config_generator import config_generator
from app.services.submission_service import submission_service
from app.core.exceptions import ValidationException, NotFoundException, QueueUnavailableException
from app.core.security import get_current_user
from app.models.user import User
from app.worker.tasks import build_submission_image

router = APIRouter(prefix="/submissions", tags=["submissions"])

ALLOWED_MIME_TYPES = {
    "application/gzip",
    "application/x-gzip",
    "application/x-tar",
    "application/zip",
    "application/x-zip-compressed",
}


@router.post("", response_model=SubmissionResponse, status_code=201)
async def submit_agent(
    package: UploadFile = File(...),
    config_data: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. 解析 config_data JSON
    try:
        config = SubmissionConfigRequest.model_validate_json(config_data)
    except json.JSONDecodeError:
        raise ValidationException("config_data 不是合法的 JSON")
    except Exception as e:
        raise ValidationException(f"配置数据校验失败: {e}")

    # 2. 校验文件类型
    if package.content_type and package.content_type not in ALLOWED_MIME_TYPES:
        raise ValidationException(f"不支持的文件类型: {package.content_type}")

    package_bytes = await package.read()
    if not package.filename:
        raise ValidationException("文件名不能为空")

    # 3. 执行完整接入流水线（校验 → 连通性 → 安全扫描 → 类型识别 → 风险定级）
    result = await submission_service.run_pipeline(
        config=config,
        package_bytes=package_bytes,
        filename=package.filename,
    )

    submission = result.submission
    submission.user_id = current_user.id
    db.add(submission)
    await db.flush()
    submission_id = str(submission.id)

    # 4-7. Store artifacts and commit atomically from the application's point
    # of view. MinIO is not transactional, so compensate uploaded objects if
    # either the second upload or the database commit fails.
    uploaded_objects: list[str] = []
    try:
        yaml_content = config_generator.generate(config)
        config_path = minio_client.upload_config(
            submission_id=submission_id, yaml_content=yaml_content
        )
        uploaded_objects.append(config_path)

        object_path, sha256_hash = minio_client.upload_package(
            submission_id=submission_id,
            file_data=package_bytes,
            filename=package.filename,
        )
        uploaded_objects.append(object_path)

        submission.source_package_path = object_path
        submission.source_package_hash = sha256_hash
        await db.flush()
        await db.commit()
        await db.refresh(submission)
    except Exception:
        await db.rollback()
        for uploaded_object in reversed(uploaded_objects):
            try:
                minio_client.delete_package(uploaded_object)
            except Exception:
                # Preserve the original failure; orphan cleanup can be retried
                # by maintenance jobs using the structured error log.
                pass
        raise

    try:
        build_submission_image.delay(submission_id)
    except Exception as exc:
        submission.status = "build_failed"
        submission.build_status = "build_failed"
        submission.status_message = "无法将镜像构建任务加入队列"
        await db.commit()
        raise QueueUnavailableException("无法将镜像构建任务加入队列") from exc

    return _build_response(submission, result)


@router.get("/{submission_id}/status", response_model=SubmissionStatusResponse)
async def get_submission_status(
    submission_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    submission = await db.get(Submission, submission_id)
    if not submission:
        raise NotFoundException(f"Submission {submission_id} 不存在")
    if submission.user_id != current_user.id and current_user.role != "admin":
        raise NotFoundException(f"Submission {submission_id} 不存在")

    return _build_status_response(submission)


@router.get("/{submission_id}/build-log", response_class=PlainTextResponse)
async def get_build_log(
    submission_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    submission = await _owned_submission(db, submission_id, current_user)
    if not submission.build_log_path:
        raise NotFoundException("构建日志尚不可用")
    return PlainTextResponse(minio_client.get_package(submission.build_log_path).decode("utf-8", errors="replace"))


@router.get("/{submission_id}/image-scan", response_class=JSONResponse)
async def get_image_scan(
    submission_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    submission = await _owned_submission(db, submission_id, current_user)
    if not submission.image_scan_path:
        raise NotFoundException("镜像扫描报告尚不可用")
    return JSONResponse(minio_client.get_json(submission.image_scan_path))


@router.get("/{submission_id}/sbom", response_class=JSONResponse)
async def get_sbom(
    submission_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    submission = await _owned_submission(db, submission_id, current_user)
    if not submission.sbom_path:
        raise NotFoundException("SBOM 尚不可用")
    return JSONResponse(minio_client.get_json(submission.sbom_path))


async def _owned_submission(db: AsyncSession, submission_id: str, current_user: User) -> Submission:
    submission = await db.get(Submission, submission_id)
    if not submission or (submission.user_id != current_user.id and current_user.role != "admin"):
        raise NotFoundException(f"Submission {submission_id} 不存在")
    return submission


def _build_tool_info(result) -> list[ToolInfo]:
    return [
        ToolInfo(id=t.id, name=t.name, category=t.category, risk_level=t.risk_level)
        for t in result.matched_tools
    ]


def _build_response(submission: Submission, result) -> SubmissionResponse:
    return SubmissionResponse(
        id=str(submission.id),
        agent_name=submission.agent_name,
        version=submission.version,
        agent_type=submission.agent_type,
        horizon=submission.horizon,
        subtype=submission.subtype,
        risk_level=submission.risk_level,
        status=submission.status,
        status_message=submission.status_message,
        build_mode=submission.build_mode,
        deployment_type=submission.deployment_type,
        entry_service=submission.entry_service,
        build_status=submission.build_status,
        runtime_protocol=submission.runtime_protocol,
        image_digest=submission.image_digest,
        matched_tools=_build_tool_info(result),
        risk_reasons=result.risk_assessment.reasons if result.risk_assessment else [],
        created_at=submission.created_at,
    )


def _build_status_response(submission: Submission) -> SubmissionStatusResponse:
    return SubmissionStatusResponse(
        id=str(submission.id),
        agent_name=submission.agent_name,
        agent_type=submission.agent_type,
        status=submission.status,
        risk_level=submission.risk_level,
        status_message=submission.status_message,
        build_mode=submission.build_mode,
        deployment_type=submission.deployment_type,
        compose_file=submission.compose_file,
        entry_service=submission.entry_service,
        build_status=submission.build_status,
        runtime_protocol=submission.runtime_protocol,
        image_ref=submission.image_ref,
        image_digest=submission.image_digest,
        dockerfile_path=submission.dockerfile_path,
        build_log_path=submission.build_log_path,
        sbom_path=submission.sbom_path,
        image_scan_path=submission.image_scan_path,
        config=submission.config,
        created_at=submission.created_at,
        updated_at=submission.updated_at,
    )
