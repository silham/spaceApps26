"""Runtime settings loaded from environment / .env (see .env.example)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", env_prefix="FTM_", extra="ignore")

    database_url: str = "postgresql+psycopg://ftm:ftm@localhost:5432/ftm"
    data_dir: Path = REPO_ROOT / "data"
    results_dir: Path = REPO_ROOT / "results"
    cors_origins: list[str] = ["http://localhost:5173"]
    demo_mode: bool = True

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def fixtures_dir(self) -> Path:
        return self.data_dir / "fixtures"


@lru_cache
def get_settings() -> Settings:
    return Settings()
