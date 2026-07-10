from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_current_user
from app.core import rag
from app.models.user import User
from app.models.bot import Bot
from app.schemas.bot import BotCreate, BotOut, ChatRequest, ChatResponse

router = APIRouter()


@router.get("", response_model=list[BotOut])
def list_bots(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Bot).filter(Bot.organization_id == user.organization_id).all()


@router.post("", response_model=BotOut, status_code=201)
def create_bot(payload: BotCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    bot = Bot(organization_id=user.organization_id, **payload.model_dump(exclude_none=True))
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return bot


def _get_owned_bot(bot_id: int, db: Session, user: User) -> Bot:
    bot = (
        db.query(Bot)
        .filter(Bot.id == bot_id, Bot.organization_id == user.organization_id)
        .first()
    )
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot


@router.post("/{bot_id}/chat", response_model=ChatResponse)
def chat(
    bot_id: int,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Dashboard test harness — ask the bot a question through the RAG engine."""
    bot = _get_owned_bot(bot_id, db, user)
    return ChatResponse(answer=rag.answer_question(db, bot, payload.question))
