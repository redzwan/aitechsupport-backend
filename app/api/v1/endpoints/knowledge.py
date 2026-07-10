from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_current_user
from app.core import embeddings, ingest, loaders
from app.core.settings import settings
from app.models.user import User
from app.models.bot import Bot
from app.models.knowledge import KnowledgeSource, Chunk
from app.schemas.knowledge import KnowledgeCreate, KnowledgeOut

router = APIRouter()

_READ_CHUNK = 64 * 1024


def _owned_bot(bot_id: int, db: Session, user: User) -> Bot:
    bot = (
        db.query(Bot)
        .filter(Bot.id == bot_id, Bot.organization_id == user.organization_id)
        .first()
    )
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot


def _require_embeddings() -> None:
    if not embeddings.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Embeddings not configured: set VOYAGE_API_KEY (or EMBEDDINGS_PROVIDER=fake for dev).",
        )


def _out(src: KnowledgeSource, chunk_count: int) -> KnowledgeOut:
    return KnowledgeOut(
        id=src.id,
        organization_id=src.organization_id,
        bot_id=src.bot_id,
        source_type=src.source_type,
        title=src.title,
        location=src.location,
        status=src.status,
        chunk_count=chunk_count,
    )


async def _read_capped(file: UploadFile, limit: int) -> bytes:
    """Read an upload in bounded chunks, rejecting once it exceeds `limit`."""
    buf = bytearray()
    while True:
        part = await file.read(_READ_CHUNK)
        if not part:
            break
        buf.extend(part)
        if len(buf) > limit:
            raise HTTPException(status_code=413, detail="File too large")
    return bytes(buf)


@router.post("/bots/{bot_id}/knowledge", response_model=KnowledgeOut, status_code=201)
def add_knowledge(
    bot_id: int,
    payload: KnowledgeCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add a URL or pasted text as a knowledge source; ingestion runs in the background."""
    _require_embeddings()
    bot = _owned_bot(bot_id, db, user)

    if payload.source_type == "url":
        # Pre-validate (scheme + host not internal) so obvious SSRF/bad URLs fail
        # fast with 422 instead of a background "failed" status. load_url re-checks
        # every redirect hop too.
        try:
            loaders.validate_url(payload.location)
        except loaders.UrlNotAllowed as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    elif payload.source_type == "text":
        if len(payload.text.encode("utf-8")) > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Text too large")

    src = KnowledgeSource(
        organization_id=user.organization_id,
        bot_id=bot.id,
        source_type=payload.source_type,
        title=payload.title,
        location=payload.location,
        status="pending",
    )
    db.add(src)
    db.commit()
    db.refresh(src)

    background.add_task(
        ingest.ingest_source,
        source_id=src.id,
        source_type=src.source_type,
        location=src.location,
        raw_text=payload.text,
    )
    return _out(src, 0)


@router.post("/bots/{bot_id}/knowledge/upload", response_model=KnowledgeOut, status_code=201)
async def upload_knowledge(
    bot_id: int,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload a text/markdown/HTML file as a knowledge source."""
    _require_embeddings()
    bot = _owned_bot(bot_id, db, user)

    data = await _read_capped(file, settings.MAX_UPLOAD_BYTES)
    title, text = loaders.load_bytes(file.filename or "upload", data)
    if not text.strip():
        raise HTTPException(status_code=422, detail="No extractable text in file")

    src = KnowledgeSource(
        organization_id=user.organization_id,
        bot_id=bot.id,
        source_type="file",
        title=title or file.filename,
        location=file.filename,
        status="pending",
    )
    db.add(src)
    db.commit()
    db.refresh(src)

    background.add_task(
        ingest.ingest_source,
        source_id=src.id,
        source_type="file",
        location=None,
        raw_text=text,
    )
    return _out(src, 0)


@router.get("/bots/{bot_id}/knowledge", response_model=list[KnowledgeOut])
def list_knowledge(
    bot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bot = _owned_bot(bot_id, db, user)
    sources = (
        db.query(KnowledgeSource)
        .filter(KnowledgeSource.bot_id == bot.id, KnowledgeSource.organization_id == user.organization_id)
        .order_by(KnowledgeSource.id.desc())
        .all()
    )
    if not sources:
        return []
    # Single aggregate query for all chunk counts (avoids an N+1 over sources).
    ids = [s.id for s in sources]
    counts = dict(
        db.query(Chunk.knowledge_source_id, func.count(Chunk.id))
        .filter(Chunk.knowledge_source_id.in_(ids))
        .group_by(Chunk.knowledge_source_id)
        .all()
    )
    return [_out(s, counts.get(s.id, 0)) for s in sources]


@router.delete("/knowledge/{source_id}", status_code=204)
def delete_knowledge(
    source_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    src = (
        db.query(KnowledgeSource)
        .filter(KnowledgeSource.id == source_id, KnowledgeSource.organization_id == user.organization_id)
        .first()
    )
    if not src:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    db.query(Chunk).filter(Chunk.knowledge_source_id == src.id).delete()
    db.delete(src)
    db.commit()
