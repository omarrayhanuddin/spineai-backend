import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, EmailStr


class Settings(BaseSettings):
    EMBEDDING_DIMENSIONS: int = Field(default=1536)
    APP_ENV: str = Field(default="stage", env="APP_ENV")
    STRIPE_API_KEY: str = Field(default=None, env="STRIPE_API_KEY")
    STRIPE_WEBHOOK_SECRET: str = Field(default=None, env="STRIPE_WEBHOOK_SECRET")
    STRIPE_SUCCESS_URL: str = Field(default=None, env="STRIPE_SUCCESS_URL")
    STRIPE_CANCEL_URL: str = Field(default=None, env="STRIPE_CANCEL_URL")

    DATABASE_URL: str = Field(..., env=["DATABASE_URL", "DB_URL"])
    MISTRAL_API_KEY: str | None = Field(default=None, env="MISTRAL_API_KEY")
    DOCUMENT_INTELLIGENCE_API_KEY: str | None = Field(
        default=None, env="DOCUMENT_INTELLIGENCE_API_KEY"
    )
    DOCUMENT_INTELLIGENCE_ENDPOINT: str | None = Field(
        default=None, env="DOCUMENT_INTELLIGENCE_ENDPOINT"
    )
    OPENAI_API_KEY: str | None = Field(default=None, env="OPENAI_API_KEY")
    JWT_SECRET_KEY: str | None = Field(default="your-secret-key", env="JWT_SECRET_KEY")
    S3_ACCESS_KEY: str | None = Field(default="your-s3-access-key", env="S3_ACCESS_KEY")
    S3_SECRET_KEY: str | None = Field(default="your-s3-secret-key", env="S3_SECRET_KEY")
    S3_REGION: str | None = Field(default="your-s3-region", env="S3_REGION")
    ALGORITHM: str = Field(default="HS256", env="ALGORITHM")
    DEBUG_MODE: bool = Field(default=False, env="DEBUG_MODE")
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    SITE_DOMIN: str = Field(default="http://127.0.0.1:8000", env="SITE_DOMIN")
    OPENAI_VECTOR_SIZE: int = 1536

    # Email settings
    SMTP_HOST: str = Field(default="smtp.gmail.com", env="SMTP_HOST")
    SMTP_PORT: int = Field(default=465, env="SMTP_PORT")
    SMTP_USER: EmailStr = Field(..., env="SMTP_USER")
    SMTP_PASSWORD: str = Field(..., env="SMTP_PASSWORD")
    FROM_EMAIL: EmailStr = Field(
        default_factory=lambda: os.getenv("SMTP_USER", ""), env="FROM_EMAIL"
    )
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/0", env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/0", env="CELERY_RESULT_BACKEND")
    TREATMENT_PLAN_PRICE_ID: str | None = Field(default="price_1Rj0RVFjPe0daNEdsVAfoJsL", env="TREATMENT_PLAN_PRICE_ID")


    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
