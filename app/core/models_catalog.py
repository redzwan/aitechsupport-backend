"""Catalog of selectable chat models (OpenRouter ids).

These ids are suggestions for the admin UI dropdown; a bot's `chat_model` is a
free-text field, so an admin can enter any OpenRouter model id if a slug here
drifts. Verify exact slugs at https://openrouter.ai/models.
"""
from __future__ import annotations

from app.core import config_store

CHAT_MODELS: list[dict] = [
    {"id": "anthropic/claude-haiku-4.5", "label": "Claude Haiku 4.5", "provider": "Anthropic"},
    {"id": "anthropic/claude-sonnet-4.5", "label": "Claude Sonnet 4.5", "provider": "Anthropic"},
    {"id": "openai/gpt-5.4-mini", "label": "GPT-5.4 Mini", "provider": "OpenAI"},
    {"id": "openai/gpt-5.4-nano", "label": "GPT-5.4 Nano", "provider": "OpenAI"},
    {"id": "openai/gpt-oss-120b", "label": "GPT-OSS 120B", "provider": "OpenAI (open)"},
    {"id": "mistralai/mistral-small", "label": "Mistral Small", "provider": "Mistral"},
    {"id": "google/gemma-3-27b-it", "label": "Gemma 3 27B", "provider": "Google (open)"},
]

_HARDCODED_DEFAULT = "anthropic/claude-haiku-4.5"


def default_model() -> str:
    """Platform default model (settable via admin), else the hardcoded default."""
    return config_store.get("DEFAULT_CHAT_MODEL") or _HARDCODED_DEFAULT


def resolve_for_bot(chat_model: str | None) -> str:
    return chat_model or default_model()
