import pytest

from app.core.config import Settings


def test_sync_postgres_url_is_normalized_for_async_engine():
    settings = Settings(DATABASE_URL="postgresql://u:p@db/app", _env_file=None)
    assert settings.DATABASE_URL.startswith("postgresql+asyncpg://")


def test_production_rejects_default_jwt_secret():
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        Settings(ENVIRONMENT="production", JWT_SECRET_KEY="dev-secret-change-in-production-32-bytes-minimum", _env_file=None)
