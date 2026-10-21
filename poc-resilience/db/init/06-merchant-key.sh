#!/bin/sh
# =====================================================================
# Clé API du marchand de démo : prise dans le .env (MERCHANT_API_KEY), jamais dans le dépôt.
# Idempotent : à rejouer si la clé du .env change
#   docker compose exec db sh /docker-entrypoint-initdb.d/06-merchant-key.sh
# =====================================================================
set -eu

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v key="$MERCHANT_API_KEY" <<'SQL'
UPDATE merchants SET api_key = :'key' WHERE name = 'Brulerie du Comptoir';
SQL
