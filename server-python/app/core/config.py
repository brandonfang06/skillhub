from dataclasses import dataclass
import os
from pathlib import Path

DEFAULT_DATABASE_URL = "postgresql+asyncpg://skillhub:skillhub_dev@localhost:5432/skillhub"
DEFAULT_STORAGE_BASE_PATH = str(Path(__file__).resolve().parents[3] / ".dev" / "java-storage")


@dataclass(frozen=True)
class Settings:
    database_url: str
    storage_base_path: str


def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("SKILLHUB_DATABASE_URL", DEFAULT_DATABASE_URL),
        storage_base_path=os.getenv("SKILLHUB_STORAGE_BASE_PATH", DEFAULT_STORAGE_BASE_PATH),
    )
