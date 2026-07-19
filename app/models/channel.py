from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, JSON

from app.db.session import Base


class Channel(Base):
    """A messaging channel a bot answers on. MVP: WhatsApp + website widget.

    Per-tenant WhatsApp credentials (phone_number_id + access token) live here,
    NOT in .env — each organization connects its own WABA via embedded signup.
    Website-widget config (kind='widget') also lives here so Conversation.channel_id
    scopes the handoff inbox uniformly across channels.
    """

    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    bot_id = Column(Integer, ForeignKey("bots.id"), index=True, nullable=False)

    # whatsapp | widget (telegram later)
    kind = Column(String, default="whatsapp", nullable=False)

    # WhatsApp-specific
    waba_id = Column(String, nullable=True)
    phone_number_id = Column(String, index=True, nullable=True)  # inbound webhook routes on this
    access_token = Column(String, nullable=True)  # TODO: encrypt at rest before prod

    # Website-widget-specific (kind='widget')
    # Public embed key — a selector in the tenant's page HTML, NOT a secret.
    public_key = Column(String, unique=True, index=True, nullable=True)
    # Normalized "scheme://host[:port]" origins allowed to embed (browser hygiene).
    allowed_origins = Column(JSON, nullable=True)
    # Appearance blob the widget bundle renders (title, greeting, colors, position).
    appearance = Column(JSON, nullable=True)
    # Per-day message cap for this widget (blast-radius limit); null -> platform default.
    widget_daily_message_cap = Column(Integer, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
