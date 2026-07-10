from pydantic import BaseModel


class BotCreate(BaseModel):
    name: str
    system_prompt: str | None = None
    fallback_message: str | None = None


class BotOut(BaseModel):
    id: int
    organization_id: int
    name: str
    system_prompt: str | None = None
    fallback_message: str | None = None
    is_active: bool

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    """Direct test endpoint — ask a bot a question without going through a channel."""
    question: str


class ChatResponse(BaseModel):
    answer: str
