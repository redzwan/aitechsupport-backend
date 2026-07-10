from fastapi import APIRouter

from app.api.v1.endpoints import health, auth, bots, knowledge, whatsapp

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(bots.router, prefix="/bots", tags=["bots"])
# Knowledge-base routes use explicit paths (/bots/{id}/knowledge, /knowledge/{id}).
api_router.include_router(knowledge.router, tags=["knowledge"])
# Channel webhook (Meta calls this directly)
api_router.include_router(whatsapp.router, prefix="/webhooks/whatsapp", tags=["whatsapp"])
