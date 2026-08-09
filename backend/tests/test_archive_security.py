import io
import tarfile
import zipfile

import pytest

from app.core.exceptions import ValidationException
from app.infrastructure.minio import validate_and_extract
from app.services.submission_service import _cleanup_dir, _extract_package


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _tar_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("filename", "factory"),
    [("agent.zip", _zip_bytes), ("agent.tar.gz", _tar_bytes)],
)
def test_valid_package_can_be_validated_and_extracted(filename, factory):
    package = factory({"my-agent/agent.py": b"print('ok')"})

    assert validate_and_extract(package, filename) == ["my-agent/agent.py"]
    extracted = _extract_package(package, filename)
    try:
        assert (extracted / "my-agent" / "agent.py").read_bytes() == b"print('ok')"
    finally:
        _cleanup_dir(extracted)


@pytest.mark.parametrize(
    ("filename", "factory"),
    [("agent.zip", _zip_bytes), ("agent.tar.gz", _tar_bytes)],
)
def test_archive_traversal_is_rejected(filename, factory):
    package = factory({"agent.py": b"pass", "../escaped.py": b"owned"})

    with pytest.raises(ValidationException, match="非法路径|路径越界"):
        validate_and_extract(package, filename)


def test_tar_symlink_is_rejected():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        agent = tarfile.TarInfo("agent.py")
        agent.size = 4
        archive.addfile(agent, io.BytesIO(b"pass"))
        link = tarfile.TarInfo("escape")
        link.type = tarfile.SYMTYPE
        link.linkname = "../outside"
        archive.addfile(link)

    with pytest.raises(ValidationException, match="特殊文件"):
        validate_and_extract(buffer.getvalue(), "agent.tar.gz")
