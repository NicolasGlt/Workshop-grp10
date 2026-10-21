#!/bin/sh
# =====================================================================
# Back-office (consigne additionnelle 1) : rôle et schéma dédiés.
#   - backoffice : utilisé par l'app AUTH_FACIALE lancée sur le PC Hôte
#     * propriétaire du schéma backoffice (comptes, habilitations, gabarits, journal)
#     * LECTURE SEULE sur le métier (transactions, marchands, logs, commandes)
# Le mot de passe vient du .env (BACKOFFICE_DB_PASSWORD).
# Idempotent : rejouable sur une base existante
#   docker compose exec db sh /docker-entrypoint-initdb.d/05-backoffice.sh
# =====================================================================
set -eu

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v bo_pw="$BACKOFFICE_DB_PASSWORD" <<'SQL'
SELECT 'CREATE ROLE backoffice LOGIN' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'backoffice')
\gexec
ALTER ROLE backoffice PASSWORD :'bo_pw';

CREATE SCHEMA IF NOT EXISTS backoffice AUTHORIZATION backoffice;
REVOKE ALL ON SCHEMA backoffice FROM PUBLIC;

GRANT USAGE ON SCHEMA public TO backoffice;
GRANT SELECT ON transactions, commandes, logs TO backoffice;
-- Marchands sans la colonne api_key : le back-office ne voit jamais les clés API.
GRANT SELECT (id_merchant, name, id_compte_bancaire, created_at) ON merchants TO backoffice;
SQL
