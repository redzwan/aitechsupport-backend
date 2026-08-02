# AiChatSupport — Backend (FastAPI)

Multi-tenant support-chatbot SaaS. Businesses connect their content + WhatsApp
number; customers ask questions; a Claude-powered RAG engine answers, with human
handoff, conversation history, and usage-metered billing.

## Stack
- FastAPI + SQLAlchemy + Alembic
- PostgreSQL + **pgvector** (embedding search)
- Anthropic Claude (answers) · Voyage AI (embeddings)
- WhatsApp Business Cloud API (channel) · Billplz (billing)

## Local setup
Requires **Python 3.10+** (the code uses `X | None` / `list[X]` syntax). Verified on 3.11.

```bash
# 1. venv + deps
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. env
cp .env.example .env          # a local .env pointing at the Docker DB below is fine

# 3. Postgres + pgvector (Docker, port 5433 — matches .env DATABASE_URL)
chmod +x scripts/dev-db.sh
./scripts/dev-db.sh up         # starts pgvector/pgvector:pg16 + enables the extension

# 4. migrate + run
alembic upgrade head
uvicorn main:app --reload --port 8100
```
Docs: http://localhost:8100/docs · Health: http://localhost:8100/api/v1/health

DB helpers: `./scripts/dev-db.sh {up|down|psql|reset}`.
The RAG `/chat` endpoint returns **503** until `VOYAGE_API_KEY` and `ANTHROPIC_API_KEY` are set in `.env`.

## Layout
```
main.py                 FastAPI app bootstrap (CORS, router, health)
app/core/               settings, security (JWT), llm (Claude), rag (retrieve+answer)
app/db/session.py       engine, SessionLocal, Base, get_db
app/models/             SQLAlchemy models (tenant-scoped)
app/schemas/            Pydantic request/response models
app/api/v1/             api_router + endpoints/{health,auth,bots,whatsapp}
alembic/                migrations
```

## Deployment
Hosted on the shared VPS (srv1275698, user `realestate`) behind nginx as a
systemd service, deployed via a `~/deploy-backend.sh` git-pull script — same
pattern as Realesta. Domain: `api.aichatsupport.my`.

See `../PROJECT_STATE.md` for the phased roadmap and current status.
