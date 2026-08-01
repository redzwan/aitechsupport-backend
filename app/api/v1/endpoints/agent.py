"""Agent-facing endpoints that span an org's whole fleet of bots/sites.

The per-bot inbox lives under /bots/{id}/conversations; this module adds the
org-WIDE queue so one human sees every site's needs-human conversations in a
single merged list. Claim/reply/release stay bot-scoped (each row carries its
bot_id so the client knows which path to POST to)."""
import asyncio
import json
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Session

from app.db.session import get_db, SessionLocal
from app.api.deps import get_agent_user
from app.core.events import bus, org_topic, user_topic
from app.core import presence
from app.models.user import User
from app.models.bot import Bot
from app.models.channel import Channel
from app.models.conversation import Conversation, Message
from app.models.internal_message import InternalMessage
from app.models.game_session import GameSession
from app.schemas.widget import QueueRow
from app.schemas.presence import PresenceUpdate, PresenceRow
from app.schemas.chat import DmSend, DmOut
from app.schemas.game import GameCreate, MoveSend, GameOut

router = APIRouter()

QUEUE_LIMIT = 200
# Presence rules live in app.core.presence — the public widget reads the same
# heartbeat to decide whether "Talk to a human" can be offered at all.
HEARTBEAT_TTL = presence.HEARTBEAT_TTL


@router.get("/queue", response_model=list[QueueRow])
def agent_queue(
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_agent_user),
):
    """Every conversation across all of the org's bots (newest first), optionally
    filtered by status (e.g. needs_human). Each row is tagged with its bot/site."""
    org_id = user.organization_id
    q = db.query(Conversation).filter(Conversation.organization_id == org_id)
    if status:
        q = q.filter(Conversation.status == status)
    convs = q.order_by(Conversation.last_message_at.desc()).limit(QUEUE_LIMIT).all()
    if not convs:
        return []

    ids = [c.id for c in convs]
    counts = dict(
        db.query(Message.conversation_id, func.count(Message.id))
        .filter(Message.conversation_id.in_(ids))
        .group_by(Message.conversation_id)
        .all()
    )
    bot_names = {b.id: b.name for b in db.query(Bot).filter(Bot.organization_id == org_id).all()}
    kinds = {
        ch.id: ch.kind
        for ch in db.query(Channel).join(Bot, Channel.bot_id == Bot.id)
        .filter(Bot.organization_id == org_id).all()
    }
    assignee_ids = {c.assigned_user_id for c in convs if c.assigned_user_id}
    names = {}
    if assignee_ids:
        for u in db.query(User).filter(User.id.in_(assignee_ids)).all():
            names[u.id] = u.full_name or u.email

    return [
        QueueRow(
            id=c.id,
            status=c.status,
            channel_kind=kinds.get(c.channel_id),
            contact_name=c.contact_name,
            contact_email=c.contact_email,
            contact_phone=c.contact_phone,
            source_url=c.source_url,
            needs_human_at=c.needs_human_at,
            assigned_user_id=c.assigned_user_id,
            assignee_name=names.get(c.assigned_user_id),
            last_message_at=c.last_message_at,
            created_at=c.created_at,
            message_count=counts.get(c.id, 0),
            bot_id=c.bot_id,
            bot_name=bot_names.get(c.bot_id, f"Bot #{c.bot_id}"),
        )
        for c in convs
    ]


# ===== Presence (heartbeat + roster) =====

def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


_busy_user_ids = presence.busy_user_ids
_effective_status = presence.effective_status


def _presence_event(user: User, is_busy: bool) -> dict:
    return {
        "type": "presence",
        "user_id": user.id,
        "name": user.full_name or user.email,
        "role": user.role,
        "status": _effective_status(user, datetime.utcnow(), is_busy),
        "last_seen_at": user.last_seen_at.isoformat() if user.last_seen_at else None,
    }


def _publish_presence(db: Session, user: User) -> None:
    is_busy = user.id in _busy_user_ids(db, user.organization_id)
    bus.publish(org_topic(user.organization_id), _presence_event(user, is_busy))


@router.get("/presence", response_model=list[PresenceRow])
def get_presence(db: Session = Depends(get_db), user: User = Depends(get_agent_user)):
    """Org roster with EFFECTIVE presence (online/busy/away/offline)."""
    org_id = user.organization_id
    members = (
        db.query(User)
        .filter(User.organization_id == org_id, User.is_active.is_(True))
        .order_by(User.id)
        .all()
    )
    busy = _busy_user_ids(db, org_id)
    now = datetime.utcnow()
    return [
        PresenceRow(
            user_id=m.id,
            name=m.full_name or m.email,
            role=m.role,
            status=_effective_status(m, now, m.id in busy),
            last_seen_at=m.last_seen_at,
        )
        for m in members
    ]


@router.put("/presence", status_code=204)
def set_presence(payload: PresenceUpdate, db: Session = Depends(get_db), user: User = Depends(get_agent_user)):
    """Set status + refresh liveness. Doubles as the heartbeat (call every ~25s).

    "offline" is a deliberate sign-off (app backgrounded, quit, logged out) and is
    the one status that does NOT refresh liveness — it clears last_seen_at so the
    agent reads offline at once. Without it the visitor-facing widget would keep
    promising a human for the length of the heartbeat window after the last agent
    put their phone away.
    """
    if payload.status == "offline":
        user.presence_status = "offline"
        user.last_seen_at = None
        db.commit()
        _publish_presence(db, user)
        return

    status = payload.status if payload.status in ("online", "busy", "away") else "online"
    user.presence_status = status
    user.last_seen_at = datetime.utcnow()
    db.commit()
    _publish_presence(db, user)


def _touch_online(uid: int) -> None:
    """Refresh last_seen (+ mark online if unset) and broadcast presence. Own session."""
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == uid).first()
        if u is None:
            return
        u.last_seen_at = datetime.utcnow()
        if not u.presence_status:
            u.presence_status = "online"
        db.commit()
        _publish_presence(db, u)
    finally:
        db.close()


# ===== 1:1 direct messages between agents =====

@router.get("/chat", response_model=list[DmOut])
def list_dms(
    after: int = 0,
    with_user: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_agent_user),
):
    """DMs involving the caller (id > after), optionally filtered to one peer.
    Used for the initial load, per-peer thread history, and reconnect catch-up."""
    q = db.query(InternalMessage).filter(
        InternalMessage.organization_id == user.organization_id,
        or_(InternalMessage.from_user_id == user.id, InternalMessage.to_user_id == user.id),
        InternalMessage.id > max(0, after),
    )
    if with_user is not None:
        q = q.filter(
            or_(
                and_(InternalMessage.from_user_id == user.id, InternalMessage.to_user_id == with_user),
                and_(InternalMessage.from_user_id == with_user, InternalMessage.to_user_id == user.id),
            )
        )
    rows = q.order_by(InternalMessage.id.asc()).limit(300).all()
    sender_ids = {r.from_user_id for r in rows}
    names = (
        {u.id: (u.full_name or u.email) for u in db.query(User).filter(User.id.in_(sender_ids)).all()}
        if sender_ids else {}
    )
    return [
        DmOut(
            id=r.id,
            from_user_id=r.from_user_id,
            from_name=names.get(r.from_user_id, ""),
            to_user_id=r.to_user_id,
            content=r.content,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/chat", response_model=DmOut, status_code=201)
def send_dm(payload: DmSend, db: Session = Depends(get_db), user: User = Depends(get_agent_user)):
    """Send a DM to a same-org teammate. Persisted + pushed to the peer (and the
    sender's other sessions; clients dedupe by message id)."""
    if payload.to_user_id == user.id:
        raise HTTPException(status_code=400, detail="You can't message yourself.")
    peer = (
        db.query(User)
        .filter(
            User.id == payload.to_user_id,
            User.organization_id == user.organization_id,
            User.is_active.is_(True),
        )
        .first()
    )
    if peer is None or peer.role not in ("owner", "admin", "agent"):
        raise HTTPException(status_code=404, detail="Teammate not found")

    msg = InternalMessage(
        organization_id=user.organization_id,
        from_user_id=user.id,
        to_user_id=peer.id,
        content=payload.content,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    from_name = user.full_name or user.email
    event = {
        "type": "chat",
        "id": msg.id,
        "from_user_id": user.id,
        "from_name": from_name,
        "to_user_id": peer.id,
        "content": msg.content,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }
    bus.publish(user_topic(peer.id), event)   # the recipient
    bus.publish(user_topic(user.id), event)   # sender's other devices (deduped by id)
    return DmOut(
        id=msg.id,
        from_user_id=user.id,
        from_name=from_name,
        to_user_id=peer.id,
        content=msg.content,
        created_at=msg.created_at,
    )


# ===== Multiplayer chess (turn-based SAN relay) =====

def _game_names(db: Session, g: GameSession) -> dict:
    users = db.query(User).filter(User.id.in_([g.white_user_id, g.black_user_id])).all()
    return {u.id: (u.full_name or u.email) for u in users}


def _game_out(g: GameSession, db: Session, viewer_id: int) -> GameOut:
    moves = json.loads(g.moves or "[]")
    names = _game_names(db, g)
    return GameOut(
        id=g.id,
        kind=g.kind,
        white_user_id=g.white_user_id,
        black_user_id=g.black_user_id,
        white_name=names.get(g.white_user_id, ""),
        black_name=names.get(g.black_user_id, ""),
        status=g.status,
        result=g.result,
        moves=moves,
        turn="white" if len(moves) % 2 == 0 else "black",
        your_color="white" if viewer_id == g.white_user_id else "black",
        created_at=g.created_at,
    )


def _participant_game(db: Session, game_id: int, user: User) -> GameSession:
    g = (
        db.query(GameSession)
        .filter(GameSession.id == game_id, GameSession.organization_id == user.organization_id)
        .first()
    )
    if g is None or user.id not in (g.white_user_id, g.black_user_id):
        raise HTTPException(status_code=404, detail="Game not found")
    return g


@router.post("/games", response_model=GameOut, status_code=201)
def create_game(payload: GameCreate, db: Session = Depends(get_db), user: User = Depends(get_agent_user)):
    """Invite a teammate to a chess game (inviter plays white). Notifies them."""
    if payload.opponent_user_id == user.id:
        raise HTTPException(status_code=400, detail="Pick a teammate to play against.")
    opp = (
        db.query(User)
        .filter(User.id == payload.opponent_user_id, User.organization_id == user.organization_id, User.is_active.is_(True))
        .first()
    )
    if opp is None or opp.role not in ("owner", "admin", "agent"):
        raise HTTPException(status_code=404, detail="Teammate not found")

    g = GameSession(
        organization_id=user.organization_id,
        kind="chess",
        white_user_id=user.id,
        black_user_id=opp.id,
        moves="[]",
        status="active",
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    names = _game_names(db, g)
    bus.publish(user_topic(opp.id), {
        "type": "game", "event": "invite", "game_id": g.id,
        "from_user_id": user.id, "from_name": user.full_name or user.email, "to_user_id": opp.id,
        "white_user_id": g.white_user_id, "black_user_id": g.black_user_id,
        "white_name": names.get(g.white_user_id, ""), "black_name": names.get(g.black_user_id, ""),
    })
    return _game_out(g, db, user.id)


@router.get("/games/{game_id}", response_model=GameOut)
def get_game(game_id: int, db: Session = Depends(get_db), user: User = Depends(get_agent_user)):
    return _game_out(_participant_game(db, game_id, user), db, user.id)


@router.post("/games/{game_id}/move", response_model=GameOut)
def game_move(game_id: int, payload: MoveSend, db: Session = Depends(get_db), user: User = Depends(get_agent_user)):
    """Relay a SAN move. Enforces active + participant + whose-turn; legality is
    validated client-side (both run the same deterministic engine)."""
    g = _participant_game(db, game_id, user)
    if g.status != "active":
        raise HTTPException(status_code=409, detail="This game is already over.")
    my_color = "white" if user.id == g.white_user_id else "black"
    moves = json.loads(g.moves or "[]")
    turn = "white" if len(moves) % 2 == 0 else "black"
    if my_color != turn:
        raise HTTPException(status_code=409, detail="It's not your turn.")

    moves.append(payload.san)
    g.moves = json.dumps(moves)
    if payload.result in ("white", "black", "draw"):
        g.status = "finished"
        g.result = payload.result
    db.commit()
    db.refresh(g)

    opp_id = g.black_user_id if my_color == "white" else g.white_user_id
    bus.publish(user_topic(opp_id), {
        "type": "game", "event": "move", "game_id": g.id, "san": payload.san,
        "by_user_id": user.id, "ply": len(moves), "status": g.status, "result": g.result,
    })
    return _game_out(g, db, user.id)


@router.post("/games/{game_id}/resign", response_model=GameOut)
def game_resign(game_id: int, db: Session = Depends(get_db), user: User = Depends(get_agent_user)):
    """Resign — the opponent wins."""
    g = _participant_game(db, game_id, user)
    if g.status == "active":
        my_color = "white" if user.id == g.white_user_id else "black"
        g.status = "finished"
        g.result = "black" if my_color == "white" else "white"
        db.commit()
        db.refresh(g)
        opp_id = g.black_user_id if my_color == "white" else g.white_user_id
        bus.publish(user_topic(opp_id), {
            "type": "game", "event": "end", "game_id": g.id, "result": g.result, "by_user_id": user.id,
        })
    return _game_out(g, db, user.id)


# ===== Unified per-agent realtime stream =====

@router.get("/events")
async def agent_events(request: Request, user: User = Depends(get_agent_user)):
    """The single per-agent realtime stream. Multiplexes org broadcasts (ping,
    presence) and directed events (transfer / DM / game for this user) over one
    SSE. Best-effort — the client catches up from the DB on (re)connect."""
    org_id = user.organization_id
    uid = user.id
    topics = [org_topic(org_id), user_topic(uid)]

    async def gen():
        q = await bus.subscribe_many(topics)
        await run_in_threadpool(_touch_online, uid)  # mark online on connect
        last_touch = time.monotonic()
        try:
            yield _sse({"type": "connected"})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(q.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    now = time.monotonic()
                    if now - last_touch > 25:  # throttled heartbeat while connected
                        last_touch = now
                        await run_in_threadpool(_touch_online, uid)
                    continue
                yield _sse(data)
        finally:
            bus.unsubscribe_many(topics, q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

