import json
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_db
from app.infrastructure.minio import minio_client, validate_and_extract
from app.models.submission import Submission
from app.schemas.request.submission import SubmissionConfigRequest
from app.schemas.response.submission import SubmissionResponse
from app.services.api_key_vault import APIKeyVault
from app.services.config_generator import config_generator
from app.services.model_connectivity import connectivity_checker
from app.services.agent_type_identifier import agent_type_identifier
from app.core.exceptions import ValidationException

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

    # 2. 校验文件类型和大小
    if package.content_type and package.content_type not in ALLOWED_MIME_TYPES:
        raise ValidationException(f"不支持的文件类型: {package.content_type}")

    package_bytes = await package.read()
    if not package.filename:
        raise ValidationException("文件名不能为空")

    # 3. 解包校验源码结构
    validate_and_extract(package_bytes, package.filename)

    # 4. 模型连通性校验（失败则立即驳回，不消耗存储）
    connectivity = await connectivity_checker.check(
        provider=config.llm_provider,
        api_base=config.llm_api_base,
        api_key=config.llm_api_key,
        model=config.llm_model,
    )
    if not connectivity.ok:
        raise ValidationException(f"模型连通性校验失败: {connectivity.error}")

    # 5. AI 类型识别（用户留空时自动识别）
    if not config.agent_type or not config.subtype:
        identification = await agent_type_identifier.identify(config.description)
        if not config.agent_type:
            config.agent_type = identification.agent_type
        if not config.subtype:
            config.subtype = identification.subtype

    # 6. 生成 agent.config.yaml
    yaml_content = config_generator.generate(config)

    # 7. 创建 Submission 记录
    submission = Submission(
        agent_name=config.agent_name,
        version=config.version,
        agent_type=config.agent_type or "short_horizon",
        horizon="short" if config.agent_type != "long_horizon" else "long",
        subtype=config.subtype,
        risk_level="medium",
        config=config.model_dump(),
        source_package_path="",
        source_package_hash="",
        status="pending_validation",
    )
    db.add(submission)
    await db.flush()

    submission_id = str(submission.id)

    # 8. 上传源码包到 MinIO
    object_path, sha256_hash = minio_client.upload_package(
        submission_id=submission_id,
        file_data=package_bytes,
        filename=package.filename,
    )

    # 9. 上传生成的 agent.config.yaml 到 MinIO
    config_path = minio_client.upload_config(
        submission_id=submission_id, yaml_content=yaml_content
    )

    # 10. 暂存 API Key
    APIKeyVault.stash(submission_id, config.llm_api_key)

    # 11. 回填 MinIO 路径和哈希
    submission.source_package_path = object_path
    submission.source_package_hash = sha256_hash
    await db.flush()
    await db.refresh(submission)

    return submission
