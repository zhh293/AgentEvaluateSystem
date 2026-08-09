from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, model_validator
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)
    # 应用
    APP_NAME: str = "AgentEvaluateSystem"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"

    # 数据库
    DATABASE_URL: str = "postgresql+asyncpg://agenteval:devpass@localhost:5432/agent_eval"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # RabbitMQ
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672//"

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "agent-eval"
    MINIO_SECURE: bool = False

    # 沙箱
    SANDBOX_DEFAULT_TIMEOUT_SECONDS: int = 300
    SANDBOX_MAX_PACKAGE_SIZE_MB: int = 50
    SANDBOX_IMAGE_READONLY: str = "agenteval/sandbox:readonly"
    SANDBOX_IMAGE_WRITABLE: str = "agenteval/sandbox:writable"
    SANDBOX_IMAGE_HIGHRISK: str = "agenteval/sandbox:highrisk"

    # LLM-as-Judge
    JUDGE_MODEL_A: str = "gpt-4o"
    JUDGE_MODEL_B: str = "claude-sonnet-4-6"
    JUDGE_API_TIMEOUT: int = 60
    JUDGE_API_KEY: str = ""  # 系统自有 LLM API Key（用于类型识别等系统功能）
    JUDGE_API_BASE: str = "https://api.openai.com/v1"

    # 安全
    JWT_SECRET_KEY: str = "dev-secret-change-in-production-32-bytes-minimum"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    # 可观测性
    OTEL_EXPORTER_ENDPOINT: str = "http://localhost:4317"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_async_database_url(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql+psycopg2://"):
            return value.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        return value

    @model_validator(mode="after")
    def reject_insecure_production_defaults(self):
        if self.ENVIRONMENT.lower() == "production" and self.JWT_SECRET_KEY == "dev-secret-change-in-production-32-bytes-minimum":
            raise ValueError("JWT_SECRET_KEY must be changed in production")
        return self

@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
