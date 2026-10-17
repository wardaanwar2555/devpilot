"""Runtime configuration, read from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # GitHub
    github_token: str
    max_files: int
    max_file_bytes: int
    max_total_bytes: int
    # LLM (any OpenAI-compatible chat-completions API; Groq by default)
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    llm_timeout: int
    # Workflow limits
    max_retries: int
    max_patch_lines: int
    max_plan_steps: int
    # Sandbox
    sandbox_image: str
    sandbox_timeout: int
    sandbox_enabled: bool
    # Platform
    database_url: str
    api_key: str
    cors_origins: tuple[str, ...]
    rate_limit_per_hour: int
    use_langgraph: bool

    @classmethod
    def from_env(cls) -> "Settings":
        origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        return cls(
            github_token=os.getenv("GITHUB_TOKEN", ""),
            max_files=_int("MAX_FILES", 60),
            max_file_bytes=_int("MAX_FILE_BYTES", 100_000),
            max_total_bytes=_int("MAX_TOTAL_BYTES", 1_000_000),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_base_url=os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/"),
            # Model names change often: check your provider's current list.
            llm_model=os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
            llm_timeout=_int("LLM_TIMEOUT", 60),
            max_retries=_int("MAX_RETRIES", 2),
            max_patch_lines=_int("MAX_PATCH_LINES", 80),
            max_plan_steps=_int("MAX_PLAN_STEPS", 3),
            sandbox_image=os.getenv("SANDBOX_IMAGE", "devpilot-sandbox:latest"),
            sandbox_timeout=_int("SANDBOX_TIMEOUT", 60),
            sandbox_enabled=os.getenv("SANDBOX_ENABLED", "true").lower() == "true",
            database_url=os.getenv("DATABASE_URL", "sqlite:///./devpilot.db"),
            api_key=os.getenv("DEVPILOT_API_KEY", ""),
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
            rate_limit_per_hour=_int("RATE_LIMIT_PER_HOUR", 30),
            use_langgraph=os.getenv("USE_LANGGRAPH", "true").lower() == "true",
        )


def get_settings() -> Settings:
    return Settings.from_env()
