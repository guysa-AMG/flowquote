"""Global application configuration.

Single source of truth for APP_NAME, matching thresholds, and money config.
"""
import re
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "TalkQuote"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TALKQUOTE_", extra="ignore")

    app_name: str = APP_NAME
    env: str = "development"
    debug: bool = False

    # Matching thresholds (PLAN.md §8)
    min_score: float = 75.0
    min_margin: float = 15.0

    # Financial config (Never floats, integer basis points / cents)
    default_currency: str = "ZAR"  # Config-only, e.g. ZAR, GBP, USD
    default_vat_rate_bp: int = 1500  # 15.00% (basis points = rate * 100)

    # Multi-tenant default business id
    default_business_id: str = "biz_default"

    # Storage & DB
    database_path: str = "talkquote.sqlite"
    audio_storage_dir: Path = Path("storage/audio")
    audio_retention_days: int = 0  # 0 = delete immediately after processing (PLAN.md §3)

    # Inference config
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "gemma2:9b"  # or qwen2.5:7b
    whisper_model_size: str = "large-v3-turbo"  # fallback to 'small' on low CPU
    whisper_model_path: Path | None = None
    whisper_local_files_only: bool = True

    # Auth
    auth_pin: str = ""
    secret_key: str = "dev-secret-change-in-production"

    @field_validator("auth_pin")
    @classmethod
    def validate_auth_pin(cls, value: str) -> str:
        if value and not re.fullmatch(r"\d{4}", value):
            raise ValueError("TALKQUOTE_AUTH_PIN must be exactly four digits")
        return value


settings = Settings()
