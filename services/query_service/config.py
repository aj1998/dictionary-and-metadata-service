from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    MONGO_URL: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "jain_kb"
    NEO4J_URL: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j"
    NEO4J_DATABASE: str = "neo4j"
    ADMIN_USER: str
    ADMIN_PASSWORD: str
    LOG_LEVEL: str = "INFO"
    PORT: int = 8004


settings = Settings()  # type: ignore[call-arg]
