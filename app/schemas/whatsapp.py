from pydantic import BaseModel


class WhatsAppStatusOut(BaseModel):
    connection_status: str  # disconnected | pending_qr | connected
    is_active: bool
    # Whether the org's current package allows connecting WhatsApp at all —
    # lets the dashboard show an upgrade prompt instead of a broken Connect button.
    plan_allows_whatsapp: bool = True


class WhatsAppConnectOut(BaseModel):
    connection_status: str
    qr_base64: str | None = None  # None once already connected — nothing to scan
