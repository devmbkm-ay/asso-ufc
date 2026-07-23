#!/bin/sh
# Attend que PostgreSQL accepte les connexions, puis lance les migrations et l'API.
# Utilisé comme CMD dans le Dockerfile en remplacement du one-liner.

set -e

MAX_RETRIES=30
RETRY_INTERVAL=2

echo "⏳ Attente de PostgreSQL..."
i=0
until python -c "
import sys, os
from sqlalchemy import create_engine, text
try:
    engine = create_engine(os.environ['DATABASE_URL'])
    with engine.connect() as c:
        c.execute(text('SELECT 1'))
    sys.exit(0)
except Exception as e:
    print(f'  DB non prête : {e}')
    sys.exit(1)
"; do
  i=$((i+1))
  if [ $i -ge $MAX_RETRIES ]; then
    echo "❌ PostgreSQL inaccessible après ${MAX_RETRIES} tentatives. Abandon."
    exit 1
  fi
  echo "  Tentative $i/$MAX_RETRIES — nouvelle tentative dans ${RETRY_INTERVAL}s..."
  sleep $RETRY_INTERVAL
done

echo "✅ PostgreSQL prêt."
echo "🔄 Application des migrations Alembic..."
alembic upgrade head

echo "🚀 Démarrage de l'API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
