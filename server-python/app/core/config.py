from dataclasses import dataclass
import os

DEFAULT_DATABASE_URL = "postgresql+asyncpg://skillhub:skillhub_dev@localhost:5432/skillhub"


@dataclass(frozen=True)
class Settings:
    database_url: str


def get_settings() -> Settings:
    return Settings(database_url=os.getenv("SKILLHUB_DATABASE_URL", DEFAULT_DATABASE_URL))
