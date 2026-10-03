from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OV_", env_file=REPO_ROOT / ".env", extra="ignore")

    env: str = "dev"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://orchard:orchard@localhost:5433/orchardvision"
    models_dir: Path = REPO_ROOT / "models"
    data_dir: Path = REPO_ROOT / "data"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Live channel
    telemetry_hz: float = 5.0
    # Flight records
    record_hz: float = 2.0
    # A link with no telemetry for this long is reported lost
    link_timeout_s: float = 3.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
