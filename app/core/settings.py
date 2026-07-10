import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load .env early so every os.getenv() default below resolves regardless of
# module import order.
load_dotenv()


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "AiTechSupport API"

    # ===== Security =====
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecretkey123")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 8))

    # ===== Database =====
    SQLALCHEMY_DATABASE_URI: str = os.getenv(
        "DATABASE_URL",
        "postgresql://ats_admin:changeme@localhost/aitechsupport_db",
    )

    # ===== Anthropic / Claude =====
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANSWER_MODEL: str = os.getenv("ANSWER_MODEL", "claude-haiku-4-5-20251001")
    FALLBACK_MODEL: str = os.getenv("FALLBACK_MODEL", "claude-opus-4-8")

    # ===== Embeddings (Voyage AI) =====
    VOYAGE_API_KEY: str = os.getenv("VOYAGE_API_KEY", "")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "voyage-3")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", 1024))

    # ===== WhatsApp channel =====
    WHATSAPP_PROVIDER: str = os.getenv("WHATSAPP_PROVIDER", "meta")
    WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    WHATSAPP_APP_SECRET: str = os.getenv("WHATSAPP_APP_SECRET", "")

    # ===== Billing (Billplz) — OFF until the business account is live =====
    BILLING_ENABLED: bool = os.getenv("BILLING_ENABLED", "False").lower() == "true"
    BILLPLZ_API_KEY: str = os.getenv("BILLPLZ_API_KEY", "")
    BILLPLZ_X_SIGNATURE_KEY: str = os.getenv("BILLPLZ_X_SIGNATURE_KEY", "")
    BILLPLZ_COLLECTION_ID: str = os.getenv("BILLPLZ_COLLECTION_ID", "")
    BILLPLZ_SANDBOX: bool = os.getenv("BILLPLZ_SANDBOX", "True").lower() == "true"

    # ===== URLs =====
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3200")
    API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8100")

    class Config:
        case_sensitive = True


settings = Settings()


def cors_origins() -> list[str]:
    raw = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:3200,https://aitechsupport.my",
    )
    return [o.strip() for o in raw.split(",") if o.strip()]
