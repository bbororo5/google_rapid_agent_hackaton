"""Runtime settings loaded from environment.

Two modes are derived, not configured directly:
- LLM:      real ADK when EITHER Vertex AI is configured (GOOGLE_GENAI_USE_VERTEXAI
            + GOOGLE_CLOUD_PROJECT, auth via ADC) OR an AI Studio GEMINI_API_KEY
            is set. Otherwise deterministic stub.
- Evidence: real Elastic MCP when ELASTIC_MCP_URL is set, else seeded stub.

This lets the contract-enforced golden path run end-to-end offline.
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


class Settings(BaseModel):
    # --- LLM ---
    # Two auth paths: AI Studio (gemini_api_key) OR Vertex AI (ADC + project).
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"  # plain model string ADK accepts
    use_vertexai: bool = False
    google_cloud_project: str | None = None
    google_cloud_location: str = "us-central1"

    # --- Evidence (Elastic via MCP) ---
    elastic_mcp_url: str | None = None
    elastic_mcp_transport: str = "streamable_http"

    # --- Reflection export (Phoenix Cloud / Arize track) ---
    phoenix_endpoint: str | None = None
    phoenix_api_key: str | None = None
    phoenix_project: str = "launchpilot-agent"

    # --- Server ---
    port: int = 8000

    # --- Signal thresholds (UNVERIFIED placeholders, agent-tool-spec §6) ---
    signal_threshold_high: float = 2.0  # >= this lift => strong signal
    signal_threshold_low: float = 1.3   # >= this => weak signal; below => noise

    # --- Failure policy (agent-tool-spec §4) ---
    tool_max_retries: int = 2   # Class 1: cheap retries, no LLM
    backtrack_limit: int = 3    # Class 2: max review-fail re-runs before FAILED

    @property
    def use_real_llm(self) -> bool:
        # Real ADK workers run when EITHER an AI Studio key is set OR Vertex is
        # configured (ADC handles Vertex auth, so a project id is the signal).
        return bool(self.gemini_api_key) or (self.use_vertexai and bool(self.google_cloud_project))

    @property
    def use_real_elastic(self) -> bool:
        # Presence of an MCP URL is the single switch between live Elastic and seed.
        return bool(self.elastic_mcp_url)


@lru_cache
def get_settings() -> Settings:
    # Cached so every module reads one immutable Settings instance per process.
    return Settings(
        gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
        gemini_model=os.environ.get("GEMINI_MODEL") or "gemini-flash-latest",
        use_vertexai=(os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() in ("TRUE", "1")),
        google_cloud_project=os.environ.get("GOOGLE_CLOUD_PROJECT") or None,
        google_cloud_location=os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1",
        elastic_mcp_url=os.environ.get("ELASTIC_MCP_URL") or None,
        elastic_mcp_transport=os.environ.get("ELASTIC_MCP_TRANSPORT") or "streamable_http",
        phoenix_endpoint=os.environ.get("PHOENIX_COLLECTOR_ENDPOINT") or None,
        phoenix_api_key=os.environ.get("PHOENIX_API_KEY") or None,
        phoenix_project=os.environ.get("PHOENIX_PROJECT_NAME") or "launchpilot-agent",
        port=_int("PORT", 8000),
        signal_threshold_high=_float("SIGNAL_THRESHOLD_HIGH", 2.0),
        signal_threshold_low=_float("SIGNAL_THRESHOLD_LOW", 1.3),
        tool_max_retries=_int("TOOL_MAX_RETRIES", 2),
        backtrack_limit=_int("BACKTRACK_LIMIT", 3),
    )
