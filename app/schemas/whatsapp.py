from pydantic import BaseModel


class WhatsAppStatusOut(BaseModel):
    connection_status: str  # disconnected | pending_qr | connected
    is_active: bool


class WhatsAppConnectOut(BaseModel):
    connection_status: str
    qr_base64: str | None = None  # None once already connected — nothing to scan
