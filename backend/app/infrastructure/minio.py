import io
import hashlib
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

    try:
        if filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(package_data)) as zf:
                file_list = zf.namelist()
        else:
            with tarfile.open(fileobj=io.BytesIO(package_data), mode="r:gz") as tf:
                file_list = [m.name for m in tf.getmembers()]
    except (tarfile.TarError, zipfile.BadZipFile) as e:
        raise ValidationException(f"无法解压源码包: {e}")

    basenames = {Path(f).name for f in file_list}
    if "agent.py" not in basenames:
        raise ValidationException("源码包中缺少 agent.py 文件")

    return file_list
