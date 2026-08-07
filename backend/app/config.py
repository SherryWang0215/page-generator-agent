from __future__ import annotations

import os
from dotenv import load_dotenv

from pydantic import BaseModel, Field
load_dotenv()


class Settings(BaseModel):
    # -- LLM --
    openai_api_key: str | None = Field(
        default_factory=lambda: os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    )
    openai_base_url: str = Field(
        default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.deepseek.com"
    )
    openai_model: str = Field(
        default_factory=lambda: os.getenv("DEEPSEEK_MODEL")
        or os.getenv("OPENAI_MODEL")
        or "deepseek-v4-flash"
    )
    llm_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
    )

    # -- Elasticsearch --
    es_host: str = Field(
        default_factory=lambda: os.getenv("ES_HOST", "http://localhost:9200")
    )
    es_index_name: str = Field(
        default_factory=lambda: os.getenv("ES_INDEX_NAME", "pagegen_knowledge")
    )

    # -- Embedding (DashScope text-embedding-v3) --
    dashscope_api_key: str | None = Field(
        default_factory=lambda: os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    embedding_model_name: str = Field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-v3")
    )
    embedding_dim: int = Field(
        default_factory=lambda: int(os.getenv("EMBEDDING_DIM", "1024"))
    )

    # -- RAG --
    rag_top_k: int = Field(
        default_factory=lambda: int(os.getenv("RAG_TOP_K", "3"))
    )
    rag_enabled: bool = Field(
        default_factory=lambda: os.getenv("RAG_ENABLED", "true").lower() == "true"
    )

    # -- Conversation Memory --
    memory_enabled: bool = Field(
        default_factory=lambda: os.getenv("MEMORY_ENABLED", "true").lower() == "true"
    )
    memory_max_rounds: int = Field(
        default_factory=lambda: int(os.getenv("MEMORY_MAX_ROUNDS", "10"))
    )
    es_conversation_index: str = Field(
        default_factory=lambda: os.getenv("ES_CONVERSATION_INDEX", "pagegen_conversations")
    )
    es_message_index: str = Field(
        default_factory=lambda: os.getenv("ES_MESSAGE_INDEX", "pagegen_messages")
    )
    es_profile_index: str = Field(
        default_factory=lambda: os.getenv("ES_PROFILE_INDEX", "pagegen_user_profiles")
    )
    profile_extraction_trigger_count: int = Field(
        default_factory=lambda: int(os.getenv("PROFILE_EXTRACTION_TRIGGER_COUNT", "20"))
    )
    profile_confidence_threshold: float = Field(
        default_factory=lambda: float(os.getenv("PROFILE_CONFIDENCE_THRESHOLD", "0.6"))
    )

    # -- Conversation Summary --
    summary_enabled: bool = Field(
        default_factory=lambda: os.getenv("SUMMARY_ENABLED", "true").lower() == "true"
    )
    summary_trigger_rounds: int = Field(
        default_factory=lambda: int(os.getenv("SUMMARY_TRIGGER_ROUNDS", "5"))
    )

    # -- Conversation Search --
    search_enabled: bool = Field(
        default_factory=lambda: os.getenv("SEARCH_ENABLED", "true").lower() == "true"
    )
    search_embed_messages: bool = Field(
        default_factory=lambda: os.getenv("SEARCH_EMBED_MESSAGES", "true").lower() == "true"
    )
    search_top_k: int = Field(
        default_factory=lambda: int(os.getenv("SEARCH_TOP_K", "10"))
    )

    # -- Celery execution --
    celery_broker_url: str = Field(
        default_factory=lambda: os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    )
    celery_result_backend: str = Field(
        default_factory=lambda: os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
    )
    celery_task_always_eager: bool = Field(
        default_factory=lambda: os.getenv("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true"
    )

    # -- Governance / Safety / Observability --
    audit_log_path: str = Field(
        default_factory=lambda: os.getenv("AUDIT_LOG_PATH", "data/audit/agent_audit.jsonl")
    )
    safety_enabled: bool = Field(
        default_factory=lambda: os.getenv("SAFETY_ENABLED", "true").lower() == "true"
    )
    tool_permissions_enabled: bool = Field(
        default_factory=lambda: os.getenv("TOOL_PERMISSIONS_ENABLED", "true").lower() == "true"
    )
    allowed_tool_permissions: str = Field(
        default_factory=lambda: os.getenv("ALLOWED_TOOL_PERMISSIONS", "read_page_dsl,read_write_page_dsl")
    )
    rag_min_score: float = Field(
        default_factory=lambda: float(os.getenv("RAG_MIN_SCORE", "0.0"))
    )
    langsmith_api_key: str | None = Field(
        default_factory=lambda: os.getenv("LANGSMITH_API_KEY")
    )
    langsmith_endpoint: str = Field(
        default_factory=lambda: os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    )
    langsmith_project: str = Field(
        default_factory=lambda: os.getenv("LANGSMITH_PROJECT", "page-generator-agent")
    )
    langsmith_enabled: bool = Field(
        default_factory=lambda: os.getenv("LANGSMITH_ENABLED", "false").lower() == "true"
    )

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def allowed_tool_permission_set(self) -> set[str]:
        return {
            item.strip()
            for item in self.allowed_tool_permissions.split(",")
            if item.strip()
        }


settings = Settings()
