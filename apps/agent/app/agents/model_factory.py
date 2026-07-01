"""ADK model selection for Gemini and local Ollama-backed LLMs."""
from __future__ import annotations

from functools import cached_property

from app.config import Settings


def build_model(settings: Settings):
    if settings.llm_provider in ("ollama", "local"):
        from google.adk.models.lite_llm import LiteLlm

        return LiteLlm(model=settings.local_llm_model, think=False)

    from google.adk.models import Gemini
    from google.genai import Client

    model_id = settings.gemini_model
    if settings.use_enterpriseai:
        class EnterpriseGemini(Gemini):
            @cached_property
            def api_client(self) -> Client:
                return Client(
                    enterprise=True,
                    project=settings.google_cloud_project,
                    location=settings.google_cloud_location,
                )

        return EnterpriseGemini(model=model_id)

    return model_id


def build_planner(settings: Settings):
    if settings.llm_provider in ("ollama", "local"):
        return None

    from google.adk.planners import BuiltInPlanner
    from google.genai import types

    if settings.gemini_thinking_budget is not None:
        return BuiltInPlanner(
            thinking_config=types.ThinkingConfig(
                thinking_budget=settings.gemini_thinking_budget,
                include_thoughts=False,
            )
        )
    if settings.gemini_thinking_level:
        thinking_level = getattr(types.ThinkingLevel, settings.gemini_thinking_level.upper())
        return BuiltInPlanner(
            thinking_config=types.ThinkingConfig(
                thinking_level=thinking_level,
                include_thoughts=False,
            )
        )
    return None
