from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey

from app.db.session import Base


class OrgInvite(Base):
    """A shareable code that lets a new user self-join an existing organization.

    The org + role come from THIS row (never the request body) so a joiner lands
    in the right tenant with the right role. Default is single-use + expiring."""

    __tablename__ = "org_invites"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    code = Column(String, unique=True, index=True, nullable=False)
    # Role granted to the joiner. Capped to agent|admin — an invite can NEVER mint an owner.
    role = Column(String, default="agent", nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    max_uses = Column(Integer, nullable=True)  # null = unlimited
    uses = Column(Integer, default=0, nullable=False)
    expires_at = Column(DateTime, nullable=True)  # null = never
    is_active = Column(Boolean, default=True, nullable=False)  # revoked -> False

    created_at = Column(DateTime, default=datetime.utcnow)
