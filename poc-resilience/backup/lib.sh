# Fonctions communes à backup.sh et restore.sh, sourcées, jamais lancées seules.
# Tout passe par le conteneur db : aucun client PostgreSQL requis sur l'hôte.
# Les identifiants restent dans le conteneur (POSTGRES_USER, POSTGRES_DB, socket local).

# Git Bash (Windows) convertit les chemins /tmp/... passés à docker.exe : on l'en empêche
export MSYS_NO_PATHCONV=1

COMPOSE="${COMPOSE:-docker compose}"
# Surcharge possible, ex. DB_EXEC="podman exec -i resilience-alpha_db_1"
DB_EXEC="${DB_EXEC:-$COMPOSE exec -T db}"
DUMP_DIR="${DUMP_DIR:-backup/dumps}"
KEEP="${KEEP:-7}"

# Exécute un script sh dans le conteneur db
dbsh() { $DB_EXEC sh -c "$1"; }

# Lit une commande SQL sur stdin et l'exécute dans la base $1 (vide = base de prod)
dbsql() {
  $DB_EXEC sh -c "psql -X -q -At -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d \"${1:-\$POSTGRES_DB}\""
}

# Nom de la base de prod, lu dans le conteneur
db_name() { dbsh 'printf %s "$POSTGRES_DB"'; }

# Requête de comptage exact de chaque table, une ligne "schema.table<TAB>nombre"
COUNTS_SQL="SELECT format('%s.%s', table_schema, table_name) || E'\t' ||
  (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %I.%I',
    table_schema, table_name), false, true, '')))[1]::text
FROM information_schema.tables
WHERE table_type = 'BASE TABLE' AND table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1;"

# Comptes de lignes de la base $1 (vide = base de prod)
counts() { printf '%s\n' "$COUNTS_SQL" | dbsql "${1:-}"; }

# Nombre de lignes d'une table dans un fichier de comptes
count_of() { awk -F'\t' -v t="$1" '$1 == t { print $2 }' "$2"; }

now_ms() { date +%s%3N; }

die() { echo "ERREUR : $*" >&2; exit 1; }
