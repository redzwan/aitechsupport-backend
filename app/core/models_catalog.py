"""Catalog of selectable chat models.

Ids are suggestions for the admin Packages UI dropdown; an admin can enter any id
as free text too. For the self-hosted path these are Ollama model tags served from
a package's own self_hosted_base_url; for the external path they are OpenRouter ids
(verify slugs at https://openrouter.ai/models).

Model choice is a package (plan) decision, not a customer one — see resolve_for_bot().
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.core import config_store

if TYPE_CHECKING:
    from app.models.bot import Bot
    from app.models.package import Package

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
    {"id": "openai/gpt-oss-20b:free", "label": "GPT-OSS 20B (free)", "provider": "OpenAI (open)"},
    {"id": "mistralai/mistral-small", "label": "Mistral Small", "provider": "Mistral"},
]

_HARDCODED_DEFAULT = "anthropic/claude-haiku-4.5"

# The real OpenRouter API — independent of the ambient global OPENROUTER_BASE_URL
# setting, which an admin may have repointed at a self-hosted Ollama server as the
# platform-wide default (see settings.py). A package explicitly configured for
# "openrouter" must always reach actual OpenRouter, never wherever that ambient
# default happens to point.
_REAL_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def default_model() -> str:
    """Platform default model (settable via admin), else the hardcoded default."""
    return config_store.get("DEFAULT_CHAT_MODEL") or _HARDCODED_DEFAULT


def resolve_for_bot(bot: "Bot", package: "Package | None") -> tuple[str, str | None]:
    """Resolve (model_id, base_url_override) for a bot's next answer.

    Precedence: bot.chat_model (admin-only override, not customer-editable) ->
    the org's package model -> the platform default. base_url_override pins the
    request to where the package says the model actually lives: a self-hosted
    package's own Ollama server, or real OpenRouter for an "openrouter" package.
    Only a bot with no package at all (should not happen in practice) falls
    through to the ambient global default.
    """
    model = bot.chat_model or (package.chat_model if package else None) or default_model()
    base_url = None
    if package and package.model_provider == "self_hosted" and package.self_hosted_base_url:
        base_url = package.self_hosted_base_url.rstrip("/") + "/v1"
    elif package and package.model_provider == "openrouter":
        base_url = _REAL_OPENROUTER_BASE_URL
    return model, base_url


# Vision is OFF by default: the self-hosted box can't comfortably host a VLM, so
# an image is handed to a human instead of being guessed at. Set VISION_MODEL (a
# platform-admin setting, deliberately NOT per-bot) to a vision-capable model to
# turn AI image reading on — a turn carrying an image is then forced onto it,
# since the bot's text model would silently ignore the picture.
def vision_model() -> str:
    """Model used for image turns, or "" when AI vision is disabled."""
    return (config_store.get("VISION_MODEL") or "").strip()


def vision_enabled() -> bool:
    return bool(vision_model())
