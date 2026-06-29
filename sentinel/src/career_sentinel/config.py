from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_ROOT = Path(__file__).resolve().parents[2]  # sentinel/


def data_dir() -> Path:
    return Path(os.getenv("SENTINEL_DATA_DIR") or (_ROOT / "data"))


def profile_dir() -> Path:
    return data_dir() / "chrome-profile"


def db_path() -> Path:
    return data_dir() / "sentinel.db"


@dataclass(frozen=True)
class LlmSettings:
    base_url: str
    api_key: str
    model: str


def llm_settings() -> LlmSettings:
    return LlmSettings(
        base_url=os.getenv("LLM_BASE_URL", ""),
        api_key=os.getenv("LLM_API_KEY", ""),
        model=os.getenv("LLM_MODEL", "anthropic/claude-sonnet-4-6"),
    )


@dataclass(frozen=True)
class FoundrySettings:
    api_key: str
    base_url: str
    model: str


def foundry_settings() -> FoundrySettings:
    return FoundrySettings(
        api_key=os.getenv("FOUNDRY_API_KEY", ""),
        base_url=os.getenv("FOUNDRY_BASE_URL", ""),
        model=os.getenv("FOUNDRY_MODEL", "claude-sonnet-4-6"),
    )


def llm_provider() -> str:
    """依 .env 偵測 LLM provider：有 FOUNDRY_API_KEY→foundry、否則有 LLM_API_KEY→openai、否則空。"""
    if os.getenv("FOUNDRY_API_KEY"):
        return "foundry"
    if os.getenv("LLM_API_KEY"):
        return "openai"
    return ""
