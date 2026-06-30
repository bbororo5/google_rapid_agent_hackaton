"""Runtime settings loaded from environment.

Python Agent Core requires real Gemini/ADK and real Elastic-backed evidence for
runtime behavior. Missing external configuration is reported explicitly instead
of silently producing local demo output.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

# Env precedence: real process env > repo-root .env > apps/agent/.env.
# The repo-root .env is the shared one the team fills (config.py is at
# apps/agent/app/config.py, so parents[3] is the repo root in a full checkout).
# In a container only /app/app exists, so guard the lookup; env is injected by
# compose there and dotenv is simply skipped.
_here = Path(__file__).resolve()
if len(_here.parents) > 3:
    load_dotenv(_here.parents[3] / ".env")  # repo-root .env (real env still wins)
load_dotenv()  # fallback: apps/agent/.env if present (no-op when absent)


def _int(name: str, default: int) -> int:
    # Treat empty string (a blank line in .env.example) the same as unset.
    raw = os.environ.get(name)
    return int(raw) if raw else default


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _optional_int(name: str, default: int | None = None) -> int | None:
    raw = os.environ.get(name)
    return int(raw) if raw not in (None, "") else default


class Settings(BaseModel):
    # --- LLM ---
    # Two auth paths: AI Studio (gemini_api_key) OR Vertex AI (ADC + project).
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash"  # plain model string ADK accepts
    gemini_thinking_budget: int | None = None
    gemini_thinking_level: str | None = "minimal"
    use_enterpriseai: bool = False
    use_vertexai: bool = False
    google_cloud_project: str | None = None
    google_cloud_location: str = "global"

    # --- Evidence (Elastic) ---
    # Direct ES read of the same cluster Java writes (contract 03). API key is
    # optional for local Docker Elasticsearch with security disabled.
    elastic_url: str | None = None
    elastic_api_key: str | None = None
    elastic_mcp_url: str | None = None
    elastic_mcp_transport: str = "streamable_http"
    # Route evidence through the Elasticsearch MCP server (contract 04, method B:
    # the wrapper opens an MCP stdio session). Opt-in; falls back to direct ES.
    elastic_use_mcp: bool = False
    # npx package for the Elasticsearch MCP server. Default exposes esql_query +
    # es_search (the official @elastic 0.3.1 has search only, no ES|QL).
    elastic_mcp_package: str = "@tocharianou/elasticsearch-mcp"

    # --- Reflection export (Phoenix Cloud / Arize track) ---
    phoenix_endpoint: str | None = None
    phoenix_api_key: str | None = None
    phoenix_project: str = "launchpilot-agent"
    # Read side (contract 06 §Reflection): query Phoenix MCP for past failure
    # patterns at session start. Opt-in; advisory only (cannot override review).
    phoenix_use_mcp: bool = False

    # --- Runtime hot tier (Redis) ---
    # Live ConversationState working copy (ADR-005). Authoritative truth stays in
    # Elastic; Redis is a volatile cache. Unset => in-process fallback store.
    redis_url: str | None = None

    # --- Server ---
    port: int = 8000

    # --- Signal thresholds (UNVERIFIED placeholders) ---
    signal_threshold_high: float = 2.0  # >= this lift => strong signal
    signal_threshold_low: float = 1.3   # >= this => weak signal; below => noise

    # --- Failure policy ---
    tool_max_retries: int = 2   # Class 1: cheap retries, no LLM
    backtrack_limit: int = 3    # Class 2: max review-fail re-runs before FAILED

    @property
    def use_real_llm(self) -> bool:
        return (
            bool(self.gemini_api_key)
            or ((self.use_vertexai or self.use_enterpriseai) and bool(self.google_cloud_project))
        )

    @property
    def use_real_elastic(self) -> bool:
        return bool(self.elastic_url)

    @property
    def use_redis(self) -> bool:
        # Redis hot tier. Unset REDIS_URL => InMemoryHotStore (offline mode).
        return bool(self.redis_url)

    @property
    def elastic_mcp_enabled(self) -> bool:
        # MCP evidence path (contract 04). Needs the flag + ES creds (the MCP
        # server is spawned via npx and authenticates to the same cluster).
        return bool(self.elastic_use_mcp and self.elastic_url and self.elastic_api_key)

    @property
    def reflection_enabled(self) -> bool:
        # Phoenix MCP read side. Needs the flag + a Phoenix API key.
        return bool(self.phoenix_use_mcp and self.phoenix_api_key)


@lru_cache
def get_settings() -> Settings:
    # Cached so every module reads one immutable Settings instance per process.
    return Settings(
        gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
        gemini_model=os.environ.get("GEMINI_MODEL") or "gemini-3.5-flash",
        gemini_thinking_budget=_optional_int("GEMINI_THINKING_BUDGET"),
        gemini_thinking_level=os.environ.get("GEMINI_THINKING_LEVEL") or "minimal",
        use_enterpriseai=(os.environ.get("GOOGLE_GENAI_USE_ENTERPRISE", "").upper() in ("TRUE", "1")),
        use_vertexai=(os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() in ("TRUE", "1")),
        google_cloud_project=os.environ.get("GOOGLE_CLOUD_PROJECT") or None,
        google_cloud_location=os.environ.get("GOOGLE_CLOUD_LOCATION") or "global",
        elastic_url=os.environ.get("ELASTIC_URL") or None,
        elastic_api_key=os.environ.get("ELASTIC_API_KEY") or None,
        elastic_mcp_url=os.environ.get("ELASTIC_MCP_URL") or None,
        elastic_mcp_transport=os.environ.get("ELASTIC_MCP_TRANSPORT") or "streamable_http",
        elastic_use_mcp=(os.environ.get("ELASTIC_USE_MCP", "").upper() in ("TRUE", "1")),
        elastic_mcp_package=os.environ.get("ELASTIC_MCP_PACKAGE") or "@tocharianou/elasticsearch-mcp",
        phoenix_endpoint=os.environ.get("PHOENIX_COLLECTOR_ENDPOINT") or None,
        phoenix_api_key=os.environ.get("PHOENIX_API_KEY") or None,
        phoenix_project=os.environ.get("PHOENIX_PROJECT_NAME") or "launchpilot-agent",
        phoenix_use_mcp=(os.environ.get("PHOENIX_USE_MCP", "").upper() in ("TRUE", "1")),
        redis_url=os.environ.get("REDIS_URL") or None,
        port=_int("PORT", 8000),
        signal_threshold_high=_float("SIGNAL_THRESHOLD_HIGH", 2.0),
        signal_threshold_low=_float("SIGNAL_THRESHOLD_LOW", 1.3),
        tool_max_retries=_int("TOOL_MAX_RETRIES", 2),
        backtrack_limit=_int("BACKTRACK_LIMIT", 3),
    )
