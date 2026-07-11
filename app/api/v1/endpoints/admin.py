from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_platform_admin
from app.core import config_store, models_catalog
from app.models.user import User
from app.schemas.setting import SettingsUpdate, SettingsOut

router = APIRouter()


def _hint(value: str) -> str | None:
    if not value:
        return None
    return "…" + value[-4:] if len(value) > 4 else "…"


@router.get("/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db), admin: User = Depends(get_platform_admin)):
    """Current platform config. Secrets are never returned in full — only set/hint."""
    ork = config_store.get("OPENROUTER_API_KEY")
    voy = config_store.get("VOYAGE_API_KEY")
    return SettingsOut(
        openrouter_api_key_set=bool(ork),
        openrouter_api_key_hint=_hint(ork),
        voyage_api_key_set=bool(voy),
        voyage_api_key_hint=_hint(voy),
        openrouter_base_url=config_store.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1",
        default_chat_model=models_catalog.default_model(),
    )


@router.put("/settings", response_model=SettingsOut)
def update_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_platform_admin),
):
    """Store provided keys. Blank/omitted fields are left unchanged."""
    field_to_key = {
        "openrouter_api_key": "OPENROUTER_API_KEY",
        "voyage_api_key": "VOYAGE_API_KEY",
        "openrouter_base_url": "OPENROUTER_BASE_URL",
        "default_chat_model": "DEFAULT_CHAT_MODEL",
    }
    updates: dict[str, str] = {}
    for field, key in field_to_key.items():
        value = getattr(payload, field)
        if value is not None and value.strip() != "":
            updates[key] = value.strip()
    if updates:
        config_store.set_many(db, updates)
    return get_settings(db=db, admin=admin)
