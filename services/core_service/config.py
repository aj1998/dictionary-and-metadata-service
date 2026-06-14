from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LANDING_SEED_KEYWORDS: list[str] = [
    "द्रव्य",
    "पर्याय",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str

    MONGO_URL: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "jain_kb"

    NEO4J_URL: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str
    NEO4J_DATABASE: str = "neo4j"
    NEO4J_USE_DEFAULT_DATABASE: bool = False

    ADMIN_USER: str
    ADMIN_PASSWORD: str
    LOG_LEVEL: str = "INFO"
    PORT: int = 8001

    ORIGINAL_SHASTRA_PDF_DIR: str | None = None

    @model_validator(mode="after")
    def apply_neo4j_database_switch(self) -> "Settings":
        if self.NEO4J_USE_DEFAULT_DATABASE:
            self.NEO4J_DATABASE = "neo4j"
        return self


settings = Settings()  # type: ignore[call-arg]
