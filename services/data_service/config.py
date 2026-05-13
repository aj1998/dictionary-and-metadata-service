from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    MONGO_URL: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "jain_kb"
    ADMIN_USER: str
    ADMIN_PASSWORD: str
    LOG_LEVEL: str = "INFO"
    PORT: int = 8002


settings = Settings()  # type: ignore[call-arg]
