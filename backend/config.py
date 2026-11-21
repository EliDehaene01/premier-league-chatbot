from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    # the repo's .env wherever the process starts (MCP hosts launch the server from elsewhere)
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    postgres_user: str = "plc"
    postgres_password: str = ""
    postgres_db: str = "plc"
    postgres_host: str = "localhost"
    postgres_port: int = 5433

    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_chat_deployment: str = ""
    azure_openai_embedding_deployment: str = ""
    embedding_dimensions: int = 1536  # text-embedding-3-small

    content_safety_endpoint: str = ""
    content_safety_api_key: str = ""

    prompt_version: str = "v3"
    eval_judge_deployment: str = ""  # LLM judge for evals; empty = the chat deployment
    recency_half_life_days: float = 14.0

    pl_season: int = 2026

    # how the chat reaches its tools: "mcp" (the Premier League MCP server, in-process unless
    # mcp_url is set) or "direct" (plain function calls, the same tools without the protocol)
    tool_transport: str = "mcp"
    mcp_url: str = ""  # e.g. http://127.0.0.1:8765/mcp for `python -m mcp_server --http`

    database_url: str = ""  # DATABASE_URL wins over the POSTGRES_* parts when set

    @property
    def dsn(self) -> str:
        return self.database_url or (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
