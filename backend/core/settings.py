from functools import lru_cache
from pathlib import Path

from pydantic import EmailStr, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / ".env"


class Settings(BaseSettings):
    APP_NAME: str
    DATABASE_URL: str
    FRONTEND_HOST: str

    # JWT Secret key
    JWT_SECRET: str
    JWT_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_MINUTES: int

    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_FROM: EmailStr
    SMTP_FROM_NAME: str
    SMTP_USERNAME: str
    SMTP_PASSWORD: SecretStr
    SMTP_SERVER: str
    SMTP_STARTTLS: bool
    SMTP_SSL_TLS: bool
    SMTP_DEBUG: bool
    USE_CREDENTIALS: bool

    RUSTFS_ACCESS_KEY: str
    RUSTFS_SECRET_KEY: str
    RUSTFS_BUCKET_NAME: str
    RUSTFS_ENDPOINT: str

        # File upload settings
    MAX_VIDEO_SIZE: int = 1024 * 1024 * 1024  # 1GB
    MAX_AUDIO_SIZE: int = 100 * 1024 * 1024   # 100MB
    ALLOWED_VIDEO_TYPES: list = ["video/mp4", "video/mpeg", "video/quicktime"]
    ALLOWED_AUDIO_TYPES: list = ["audio/mpeg", "audio/mp4", "audio/wav"]
    
    USE_BACKGROUND_TASKS: bool = True
    PRESIGNED_URL_EXPIRY: int = 3600
    
    # Logging
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        extra="ignore",
    )

    # Un-comment this lines of code to print the loaded settings
    # def __init__(self, **values):
    #     super().__init__(**values)
    #     print("\nLoaded settings:")
    #     for key, value in self.model_dump().items():
    #         print(f"{key}: {value} ({type(value).__name__})")


@lru_cache()
def get_settings() -> Settings:
    config = Settings()
    return config


if __name__ == "__main__":
    settings = get_settings()
