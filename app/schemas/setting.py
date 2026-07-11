from pydantic import BaseModel


class SettingsUpdate(BaseModel):
    """Admin submits keys to store. Omit or leave blank to keep the current value."""
    openrouter_api_key: str | None = None
    voyage_api_key: str | None = None
    openrouter_base_url: str | None = None
    default_chat_model: str | None = None


class SettingsOut(BaseModel):
    """Never returns raw secrets — only whether they're set + a last-4 hint."""
    openrouter_api_key_set: bool
    openrouter_api_key_hint: str | None = None
    voyage_api_key_set: bool
    voyage_api_key_hint: str | None = None
    openrouter_base_url: str
    default_chat_model: str


class ModelOption(BaseModel):
    id: str
    label: str
    provider: str
