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

    # Phase 6 — configurable caps / thresholds
    QUERY_KEYWORD_RESOLVE_MAX_TOKENS: int = 32
    QUERY_KEYWORD_FUZZY_MIN_SIM: float = 0.35
    QUERY_KEYWORD_FUZZY_TOP_K: int = 5

    QUERY_TOPICS_MATCH_DEFAULT_LIMIT: int = 5
    QUERY_TOPICS_MATCH_MIN_SIM: float = 0.30

    QUERY_GRAPHRAG_DEFAULT_LIMIT: int = 5
    QUERY_GRAPHRAG_DEFAULT_MAX_HOPS: int = 2

    QUERY_TOPICS_IN_SHASTRA_LIMIT: int = 25
    QUERY_SHASTRAS_FOR_TOPIC_LIMIT: int = 10


settings = Settings()  # type: ignore[call-arg]
