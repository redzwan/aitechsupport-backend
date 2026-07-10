#!/usr/bin/env bash
# Local dev Postgres + pgvector via Docker (matches .env DATABASE_URL on :5433).
# Usage: scripts/dev-db.sh [up|down|psql|reset]
set -euo pipefail

NAME=ats-postgres
IMAGE=pgvector/pgvector:pg16
DB=aitechsupport_db
USER=ats
PASS=ats_pw
PORT=5433

case "${1:-up}" in
  up)
    if docker ps -a --format '{{.Names}}' | grep -q "^${NAME}$"; then
      docker start "$NAME"
    else
      docker run -d --name "$NAME" \
        -e POSTGRES_USER=$USER -e POSTGRES_PASSWORD=$PASS -e POSTGRES_DB=$DB \
        -p ${PORT}:5432 -v ats_pgdata:/var/lib/postgresql/data "$IMAGE"
    fi
    until docker exec "$NAME" pg_isready -U $USER -d $DB >/dev/null 2>&1; do sleep 1; done
    docker exec "$NAME" psql -U $USER -d $DB -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null
    echo "Postgres+pgvector ready on localhost:${PORT} (db=$DB user=$USER)"
    ;;
  down)  docker stop "$NAME" ;;
  psql)  docker exec -it "$NAME" psql -U $USER -d $DB ;;
  reset) # DANGER: wipes all data, keeps the container
    docker exec "$NAME" psql -U $USER -d $DB -c \
      "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null
    echo "schema reset — run: alembic upgrade head" ;;
  *) echo "usage: $0 [up|down|psql|reset]"; exit 1 ;;
esac
