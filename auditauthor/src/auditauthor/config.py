from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUDIT_", env_file=".env", extra="ignore")
    data_dir: Path = Path("data")
    model: str = ""
    max_upload_mb: int = Field(default=20, ge=1, le=100)
    max_pages: int = Field(default=500, ge=1)
    max_pending_jobs: int = Field(default=8, ge=1)
    chunk_chars: int = Field(default=14000, ge=4000, le=30000)
    overlap_chars: int = Field(default=2000, ge=0, le=3000)
    model_timeout: int = Field(default=120, ge=1)
    model_attempts: int = Field(default=3, ge=1, le=5)
