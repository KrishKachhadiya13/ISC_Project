"""Configuration management for StegaGuard using Pydantic Settings."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Application configuration settings loaded from environment or defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "StegaGuard"
    VERSION: str = "0.1.0"
    DEBUG: bool = False
    API_PREFIX: str = "/api"

    # CORS configuration
    CORS_ORIGINS: list[str] = Field(default=["http://localhost:5173", "http://127.0.0.1:5173"])

    # Security and Upload limits (Section 5.2)
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB
    MAX_EMBED_PIXELS: int = 4_000_000  # 4 Megapixels
    MAX_DETECT_PIXELS: int = 16_000_000  # 16 Megapixels
    RATE_LIMIT_DEFAULT: str = "30/minute"
    MAX_BATCH_IMAGES: int = 20
    MIN_PASSWORD_LENGTH: int = 8

    # Artifact locations (relative to the backend folder unless absolute).
    MODELS_DIR: Path = BACKEND_DIR / "models"
    RESULTS_DIR: Path = BACKEND_DIR / "results"


settings = Settings()
