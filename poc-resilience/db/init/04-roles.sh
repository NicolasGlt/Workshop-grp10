#!/bin/sh
# =====================================================================
# Rôles à privilèges minimaux :
#   - app_user : utilisé par la Payment API (CRUD métier, pas de DDL)
#   - exporter : utilisé par postgres-exporter (lecture des stats uniquement)
# Les mots de passe viennent du .env (APP_DB_PASSWORD, EXPORTER_DB_PASSWORD)
# =====================================================================
set -eu

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v app_pw="$APP_DB_PASSWORD" \
     -v exp_pw="$EXPORTER_DB_PASSWORD" <<'SQL'
CREATE ROLE app_user LOGIN PASSWORD :'app_pw';
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;

CREATE ROLE exporter LOGIN PASSWORD :'exp_pw';
GRANT pg_monitor TO exporter;
SQL
