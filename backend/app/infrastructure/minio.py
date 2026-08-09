import io
import hashlib
import json
import tarfile
import zipfile
from pathlib import Path
from minio import Minio
from app.core.config import settings
from app.core.exceptions import ValidationException


class MinIOClient:
    """MinIO 对象存储客户端"""

    def __init__(self):
        self.client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self.bucket = settings.MINIO_BUCKET

    def ensure_bucket(self):
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def upload_package(self, submission_id: str, file_data: bytes, filename: str) -> tuple[str, str]:
        """上传源码包到 MinIO，返回 (object_path, sha256_hash)"""
        self.ensure_bucket()
        sha256_hash = hashlib.sha256(file_data).hexdigest()
        ext = Path(filename).suffix
        object_name = f"submissions/{submission_id}/package{ext}"
        self.client.put_object(self.bucket, object_name, io.BytesIO(file_data), len(file_data))
        return object_name, sha256_hash

    def get_package(self, object_name: str) -> bytes:
        response = self.client.get_object(self.bucket, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def upload_config(self, submission_id: str, yaml_content: str) -> str:
        """上传生成的 agent.config.yaml 到 MinIO，返回 object_path"""
        self.ensure_bucket()
        data = yaml_content.encode("utf-8")
        object_name = f"submissions/{submission_id}/agent.config.yaml"
        self.client.put_object(self.bucket, object_name, io.BytesIO(data), len(data))
        return object_name

    def delete_package(self, object_name: str):
        self.client.remove_object(self.bucket, object_name)

    def upload_json(self, object_name: str, payload: dict) -> str:
        self.ensure_bucket()
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.client.put_object(
            self.bucket,
            object_name,
            io.BytesIO(data),
            len(data),
            content_type="application/json",
        )
        return object_name

    def get_json(self, object_name: str) -> dict:
        return json.loads(self.get_package(object_name).decode("utf-8"))

    def upload_text(self, object_name: str, content: str, content_type: str = "text/plain") -> str:
        self.ensure_bucket()
        data = content.encode("utf-8")
        self.client.put_object(self.bucket, object_name, io.BytesIO(data), len(data), content_type=content_type)
        return object_name

    def upload_bytes(self, object_name: str, content: bytes, content_type: str) -> tuple[str, str]:
        self.ensure_bucket()
        digest = hashlib.sha256(content).hexdigest()
        self.client.put_object(
            self.bucket, object_name, io.BytesIO(content), len(content), content_type=content_type
        )
        return object_name, digest


minio_client = MinIOClient()

ALLOWED_EXTENSIONS = (".tar.gz", ".tgz", ".zip")
MAX_PACKAGE_SIZE = settings.SANDBOX_MAX_PACKAGE_SIZE_MB * 1024 * 1024


def validate_and_extract(package_data: bytes, filename: str) -> list[str]:
    """校验源码包结构并返回文件列表。抛出 ValidationException 若结构不合法。"""
    if len(package_data) > MAX_PACKAGE_SIZE:
        raise ValidationException(f"源码包大小超过限制 ({settings.SANDBOX_MAX_PACKAGE_SIZE_MB}MB)")

    if not any(filename.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise ValidationException(f"不支持的文件格式，仅支持 {', '.join(ALLOWED_EXTENSIONS)}")

    file_list: list[str] = []
    expanded_size = 0

    try:
        if filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(package_data)) as zf:
                file_list = zf.namelist()
                expanded_size = sum(member.file_size for member in zf.infolist())
                for member in zf.infolist():
                    _validate_archive_name(member.filename)
                    if (member.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValidationException(f"压缩包不允许符号链接: {member.filename}")
        else:
            with tarfile.open(fileobj=io.BytesIO(package_data), mode="r:gz") as tf:
                members = tf.getmembers()
                file_list = [m.name for m in members]
                expanded_size = sum(m.size for m in members if m.isfile())
                for member in members:
                    _validate_archive_name(member.name)
                    if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                        raise ValidationException(f"压缩包不允许特殊文件: {member.name}")
    except (tarfile.TarError, zipfile.BadZipFile) as e:
        raise ValidationException(f"无法解压源码包: {e}")

    if expanded_size > MAX_PACKAGE_SIZE:
        raise ValidationException(
            f"压缩包解压后大小超过限制 ({settings.SANDBOX_MAX_PACKAGE_SIZE_MB}MB)"
        )

    return file_list


def _validate_archive_name(name: str) -> None:
    normalized = name.replace("\\", "/")
    path = Path(normalized)
    if not normalized or normalized.startswith("/") or ".." in path.parts:
        raise ValidationException(f"压缩包包含非法路径: {name}")
