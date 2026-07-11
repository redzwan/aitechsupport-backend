import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_current_user
from app.core import rag, embeddings, llm, models_catalog, billing
from app.models.user import User
from app.models.bot import Bot
from app.schemas.bot import BotCreate, BotOut, ChatRequest, ChatResponse
from app.schemas.setting import ModelOption

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/models", response_model=list[ModelOption])
def list_models(user: User = Depends(get_current_user)):
    """Suggested chat models for a bot's model dropdown (any authenticated user)."""
    return models_catalog.CHAT_MODELS


@router.get("", response_model=list[BotOut])
def list_bots(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Bot).filter(Bot.organization_id == user.organization_id).all()


@router.post("", response_model=BotOut, status_code=201)
def create_bot(payload: BotCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Enforce the plan's bot limit. A missing package row is treated as the most
    # restrictive (1 bot) rather than fail-open.
    sub = billing.get_or_create_subscription(db, user.organization_id)
    pkg = billing.package_for(db, sub.plan)
    max_bots = pkg.max_bots if pkg is not None else 1
    current = db.query(Bot).filter(Bot.organization_id == user.organization_id).count()
    if current >= max_bots:
        plan_name = pkg.name if pkg is not None else sub.plan
        raise HTTPException(
            status_code=402,
            detail=f"Your {plan_name} plan allows {max_bots} bot(s). Upgrade to add more.",
        )
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
    # RAG needs embeddings (retrieve) AND a chat model via OpenRouter (generate).
    # Surface a clear 503 instead of a 500 when either isn't configured yet.
    if not embeddings.is_configured() or not llm.is_configured():
        raise HTTPException(
            status_code=503,
            detail="LLM not configured: set OPENROUTER_API_KEY and VOYAGE_API_KEY "
            "(or EMBEDDINGS_PROVIDER=fake for dev).",
        )
    # Enforce the monthly token quota before spending more.
    sub = billing.get_or_create_subscription(db, user.organization_id)
    if not billing.has_quota(db, sub):
        raise HTTPException(
            status_code=402,
            detail="Monthly token quota reached. Upgrade your plan to keep chatting.",
        )
    try:
        answer, tokens = rag.answer_question(db, bot, payload.question)
    except Exception:  # noqa: BLE001 — upstream embedding/LLM/network failure
        logger.exception("chat failed for bot %s", bot_id)
        raise HTTPException(
            status_code=502,
            detail="The assistant is temporarily unavailable. Please try again.",
        )
    if tokens:
        billing.record_usage(db, user.organization_id, tokens)
    return ChatResponse(answer=answer)
