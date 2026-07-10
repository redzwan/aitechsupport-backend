"""WhatsApp Business Cloud API webhook.

- GET  verifies the webhook subscription (Meta hub.challenge handshake).
- POST receives inbound messages. It MUST return 200 fast, so the heavy work
  (retrieve + Claude + send reply) is handed to a background task.

Fully wiring this is Phase 2 (see PROJECT_STATE.md) — signature validation,
per-tenant Channel lookup by phone_number_id, 24h-window handling, and the
outbound send via the tenant's stored access token.
"""
from fastapi import APIRouter, Request, Response, BackgroundTasks, Query

from app.core.settings import settings

router = APIRouter()


@router.get("")
def verify(
    mode: str = Query(alias="hub.mode", default=""),
    token: str = Query(alias="hub.verify_token", default=""),
    challenge: str = Query(alias="hub.challenge", default=""),
):
    """Meta calls this once when you subscribe the webhook."""
    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        return Response(content=challenge, media_type="text/plain")
    return Response(status_code=403)


@router.post("")
async def inbound(request: Request, background: BackgroundTasks):
    payload = await request.json()
    # TODO Phase 2: validate X-Hub-Signature-256 with WHATSAPP_APP_SECRET,
    # resolve the Channel by phone_number_id, enqueue RAG answer + outbound send.
    background.add_task(_handle_inbound, payload)
    return {"status": "received"}


def _handle_inbound(payload: dict) -> None:
    # Placeholder for the background worker entrypoint.
    ...
