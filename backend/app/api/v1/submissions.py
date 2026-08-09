import json

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_db
from app.infrastructure.minio import minio_client
from app.models.submission import Submission
from app.schemas.request.submission import SubmissionConfigRequest
from app.schemas.response.submission import SubmissionResponse, SubmissionStatusResponse, ToolInfo
from app.services.api_key_vault import APIKeyVault
from app.services.config_generator import config_generator
from app.services.submission_service import submission_service
from app.core.exceptions import ValidationException, NotFoundException

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
    db.add(submission)
    await db.flush()
    submission_id = str(submission.id)

    # 4. 生成 YAML 并上传到 MinIO
    yaml_content = config_generator.generate(config)
    minio_client.upload_config(submission_id=submission_id, yaml_content=yaml_content)

    # 5. 上传源码包到 MinIO
    object_path, sha256_hash = minio_client.upload_package(
        submission_id=submission_id,
        file_data=package_bytes,
        filename=package.filename,
    )

    # 6. 暂存 API Key
    APIKeyVault.stash(submission_id, config.llm_api_key)

    # 7. 回填 MinIO 路径和哈希
    submission.source_package_path = object_path
    submission.source_package_hash = sha256_hash
    await db.flush()
    await db.refresh(submission)

    return _build_response(submission, result)


@router.get("/{submission_id}/status", response_model=SubmissionStatusResponse)
async def get_submission_status(
    submission_id: str,
    db: AsyncSession = Depends(get_db),
):
    submission = await db.get(Submission, submission_id)
    if not submission:
        raise NotFoundException(f"Submission {submission_id} 不存在")

    return _build_status_response(submission)


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
        config=submission.config,
        created_at=submission.created_at,
        updated_at=submission.updated_at,
    )
