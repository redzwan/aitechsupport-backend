from pydantic import BaseModel


class StorageSettingsOut(BaseModel):
    """Never returns the secret key in full — only whether it's set + a last-4 hint."""
    endpoint: str
    access_key: str
    secret_key_set: bool
    secret_key_hint: str | None = None
    bucket: str
    secure: bool
    enabled: bool


class StorageSettingsUpdate(BaseModel):
    """Admin submits fields to store. Omit or leave blank to keep the current value."""
    endpoint: str | None = None
    access_key: str | None = None
    secret_key: str | None = None  # blank -> keep existing
    bucket: str | None = None
    secure: bool | None = None
    enabled: bool | None = None
