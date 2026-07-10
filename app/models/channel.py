from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey

from app.db.session import Base


class Channel(Base):
    """A messaging channel a bot answers on. MVP: WhatsApp.

    Per-tenant WhatsApp credentials (phone_number_id + access token) live here,
    NOT in .env — each organization connects its own WABA via embedded signup.
    """

    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    bot_id = Column(Integer, ForeignKey("bots.id"), index=True, nullable=False)

    # whatsapp (widget/telegram later)
    kind = Column(String, default="whatsapp", nullable=False)

    # WhatsApp-specific
    waba_id = Column(String, nullable=True)
    phone_number_id = Column(String, index=True, nullable=True)  # inbound webhook routes on this
    access_token = Column(String, nullable=True)  # TODO: encrypt at rest before prod

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
