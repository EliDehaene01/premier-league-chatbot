from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = "plc"
    postgres_password: str = ""
    postgres_db: str = "plc"
    postgres_host: str = "localhost"
    postgres_port: int = 5433

    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_chat_deployment: str = ""
    azure_openai_embedding_deployment: str = ""

    pl_season: int = 2026

    database_url: str = ""  # DATABASE_URL wins over the POSTGRES_* parts when set

    @property
    def dsn(self) -> str:
        return self.database_url or (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
