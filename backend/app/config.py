from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg2://agent:agent@localhost:5432/agent_platform"
    secret_key: str
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"
    cors_origins: str = "http://localhost:5173"
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_app_title: str = "Mini Agent Platform"
    llm_provider: str = "openrouter"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"
    langfuse_tracing_environment: str = "development"
    redis_url: str | None = None
    redis_cache_ttl_seconds: int = 300
    llm_max_tokens: int = 2000
    cv_extraction_max_tokens: int = 3000
    rag_max_tokens: int = 3000
    rag_tool_call_limit: int = 8
    rag_model_call_limit: int = 9
    rag_recursion_limit: int = 25
    supervisor_max_tokens: int = 3000
    supervisor_tool_call_limit: int = 6
    supervisor_model_call_limit: int = 8
    supervisor_recursion_limit: int = 25
    llm_input_cost_per_million_usd: float = 1.0
    llm_output_cost_per_million_usd: float = 5.0
    short_term_memory_messages: int = 20
    agent_tool_call_limit: int = 5
    agent_model_call_limit: int = 6
    agent_recursion_limit: int = 15
    http_tool_timeout_seconds: float = 10.0
    http_tool_max_response_bytes: int = 1_000_000
    upload_directory: str = "uploads"
    attachment_max_bytes: int = 10_000_000
    pdf_max_pages: int = 50
    pdf_max_text_characters: int = 120_000
    generated_file_max_bytes: int = 10_000_000
    text_to_pdf_max_characters: int = 80_000
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dimensions: int = 1536
    collection_chunk_characters: int = 1600
    collection_chunk_overlap: int = 200
    collection_search_results: int = 5

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
