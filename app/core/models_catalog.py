"""Catalog of selectable chat models.

Ids are suggestions for the admin UI dropdown; a bot's `chat_model` is free text,
so an admin can enter any id. For the self-hosted path these are Ollama model tags
served from the ai-server (see settings.OLLAMA_BASE_URL); for the external path they
are OpenRouter ids (verify slugs at https://openrouter.ai/models).
"""
from __future__ import annotations

from app.core import config_store

CHAT_MODELS: list[dict] = [
    # Self-hosted (Ollama on the ai-server) — the default path.
    {"id": "qwen2:latest", "label": "Qwen2 7B (local)", "provider": "Local (Ollama)"},
    {"id": "llama3.1:8b", "label": "Llama 3.1 8B (local)", "provider": "Local (Ollama)"},
    {"id": "mistral:7b", "label": "Mistral 7B (local)", "provider": "Local (Ollama)"},
    {"id": "gemma4:e4b", "label": "Gemma 3n E4B (local)", "provider": "Local (Ollama)"},
    {"id": "ecomm-agent:latest", "label": "E-comm Agent (local)", "provider": "Local (Ollama)"},
    # External (OpenRouter) — available if an OpenRouter key is configured.
    {"id": "anthropic/claude-haiku-4.5", "label": "Claude Haiku 4.5", "provider": "Anthropic"},
    {"id": "anthropic/claude-sonnet-4.5", "label": "Claude Sonnet 4.5", "provider": "Anthropic"},
    {"id": "openai/gpt-5.4-mini", "label": "GPT-5.4 Mini", "provider": "OpenAI"},
    {"id": "openai/gpt-oss-120b", "label": "GPT-OSS 120B", "provider": "OpenAI (open)"},
    {"id": "mistralai/mistral-small", "label": "Mistral Small", "provider": "Mistral"},
]

_HARDCODED_DEFAULT = "anthropic/claude-haiku-4.5"


def default_model() -> str:
    """Platform default model (settable via admin), else the hardcoded default."""
    return config_store.get("DEFAULT_CHAT_MODEL") or _HARDCODED_DEFAULT


def resolve_for_bot(chat_model: str | None) -> str:
    return chat_model or default_model()


# Only one model on the self-hosted server can read images, so a turn carrying an
# image is forced onto it regardless of the bot's configured chat model — a text
# model handed an image would silently ignore it. Platform-admin settable so it
# can be swapped when a better VLM is installed; deliberately NOT per-bot, so
# tenants can't pick a model that can't see.
_HARDCODED_VISION_DEFAULT = "qwen2.5vl:3b"


def vision_model() -> str:
    """Model used whenever a message carries an image."""
    return config_store.get("VISION_MODEL") or _HARDCODED_VISION_DEFAULT
