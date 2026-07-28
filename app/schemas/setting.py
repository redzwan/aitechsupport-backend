from pydantic import BaseModel, model_validator


class SettingsUpdate(BaseModel):
    """Admin submits keys to store. Omit or leave blank to keep the current value."""
    openrouter_api_key: str | None = None
    voyage_api_key: str | None = None
    openrouter_base_url: str | None = None
    default_chat_model: str | None = None
    fonnte_account_token: str | None = None
    field_encryption_key: str | None = None
    embeddings_provider: str | None = None  # "voyage" | "openrouter"
    embedding_model_openrouter_main: str | None = None
    embedding_model_openrouter_fallback_1: str | None = None
    embedding_model_openrouter_fallback_2: str | None = None


class SettingsOut(BaseModel):
    """Never returns raw secrets — only whether they're set + a last-4 hint."""
    openrouter_api_key_set: bool
    openrouter_api_key_hint: str | None = None
    voyage_api_key_set: bool
    voyage_api_key_hint: str | None = None
    openrouter_base_url: str
    default_chat_model: str
    fonnte_account_token_set: bool
    fonnte_account_token_hint: str | None = None
    field_encryption_key_set: bool
    embeddings_provider: str
    embedding_model_openrouter_main: str
    embedding_model_openrouter_fallback_1: str
    embedding_model_openrouter_fallback_2: str


class ModelOption(BaseModel):
    id: str
    label: str
    provider: str


class FallbackTier(BaseModel):
    """One rung of a package's chat fallback chain, tried in order until one
    answers successfully. Set per-package under Admin -> Packages."""
    label: str
    provider: str  # "self_hosted" | "openrouter"
    base_url: str | None = None  # required for self_hosted; ignored for openrouter
    model: str

    @model_validator(mode="after")
    def _validate(self) -> "FallbackTier":
        if self.provider not in ("self_hosted", "openrouter"):
            raise ValueError("provider must be 'self_hosted' or 'openrouter'")
        if self.provider == "self_hosted" and not (self.base_url or "").strip():
            raise ValueError(f"base_url is required for self-hosted tier '{self.label}'")
        if not self.model.strip():
            raise ValueError(f"model is required for tier '{self.label}'")
        return self


