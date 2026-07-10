# Import every model here so Alembic autogenerate and Base.metadata.create_all
# see all tables and their foreign keys.
from app.models.organization import Organization  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.bot import Bot  # noqa: F401
from app.models.knowledge import KnowledgeSource, Chunk  # noqa: F401
from app.models.channel import Channel  # noqa: F401
from app.models.conversation import Conversation, Message  # noqa: F401
from app.models.subscription import Subscription  # noqa: F401
