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

    # Untrusted Agent image builds. Production must use a dedicated rootless
    # builder endpoint rather than the runtime Docker daemon.
    AGENT_BUILDER_DOCKER_HOST: str = ""
    AGENT_IMAGE_REPOSITORY: str = "agenteval/submission"
    AGENT_IMAGE_PUSH: bool = False
    AGENT_REGISTRY_USERNAME: str = ""
    AGENT_REGISTRY_PASSWORD: str = ""
    AGENT_BUILD_TIMEOUT_SECONDS: int = 900
    AGENT_BUILD_NETWORK_MODE: str = "none"
    AGENT_BUILD_PULL_BASE_IMAGES: bool = True
    AGENT_BUILD_LOG_MAX_CHARS: int = 100_000
    AGENT_DOCKERFILE_MAX_BYTES: int = 256 * 1024
    AGENT_IMAGE_MAX_BYTES: int = 2 * 1024 * 1024 * 1024
    AGENT_TRIVY_PATH: str = ""
    AGENT_IMAGE_SCAN_TIMEOUT_SECONDS: int = 300
    AGENT_RUNTIME_NETWORK: str = "agenteval-runtime"
    AGENT_EGRESS_PROXY: str = "http://agenteval-egress:3128"
    AGENT_EGRESS_PROXY_CONTAINER: str = "agenteval-egress-proxy"
    AGENT_EGRESS_PROXY_IMAGE: str = "agenteval/egress-proxy:latest"
    AGENT_EGRESS_ALLOWED_DOMAINS: str = "api.openai.com,api.anthropic.com,api.deepseek.com,dashscope.aliyuncs.com,open.bigmodel.cn,api.moonshot.cn"
    AGENT_RUNTIME_USER: str = "65532:65532"
    AGENT_RUNTIME_LOW: str = ""
    AGENT_RUNTIME_MEDIUM: str = ""
    AGENT_RUNTIME_HIGH: str = ""
    AGENT_RUNTIME_MEMORY_BYTES: int = 512 * 1024 * 1024
    AGENT_RUNTIME_NANO_CPUS: int = 1_000_000_000
    AGENT_RUNTIME_PIDS_LIMIT: int = 64
    AGENT_RUNTIME_MAX_OUTPUT_BYTES: int = 10 * 1024 * 1024
    AGENT_HTTP_INVOKER_IMAGE: str = "agenteval/http-invoker:latest"

    # LLM-as-Judge
    JUDGE_MODEL_A: str = "gpt-4o"
    JUDGE_MODEL_B: str = "claude-sonnet-4-6"
    JUDGE_API_TIMEOUT: int = 60
    JUDGE_API_KEY: str = ""  # 系统自有 LLM API Key（用于类型识别等系统功能）
    JUDGE_API_BASE: str = "https://api.openai.com/v1"
    ALLOW_PRIVATE_MODEL_ENDPOINTS: bool = False
    MODEL_ENDPOINT_ALLOWED_DOMAINS: str = "api.openai.com,api.anthropic.com,api.deepseek.com,dashscope.aliyuncs.com,open.bigmodel.cn,api.moonshot.cn"

    # 安全
    JWT_SECRET_KEY: str = "dev-secret-change-in-production-32-bytes-minimum"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440
    CREDENTIAL_TTL_SECONDS: int = 3600

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
        if self.ENVIRONMENT.lower() == "production" and not self.AGENT_BUILDER_DOCKER_HOST:
            raise ValueError("AGENT_BUILDER_DOCKER_HOST must point to an isolated builder in production")
        if self.ENVIRONMENT.lower() == "production" and not self.AGENT_IMAGE_PUSH:
            raise ValueError("AGENT_IMAGE_PUSH must be enabled so isolated builders publish immutable images")
        if self.ENVIRONMENT.lower() == "production" and not self.AGENT_TRIVY_PATH:
            raise ValueError("AGENT_TRIVY_PATH must be configured for production image scanning")
        return self

@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
