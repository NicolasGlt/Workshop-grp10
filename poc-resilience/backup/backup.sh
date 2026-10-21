#!/usr/bin/env bash
# =====================================================================
# Sauvegarde de la base de prod (payments) : pg_dump -Fc horodaté,
# empreinte SHA-256, comptes de lignes pris dans le MÊME snapshot que le
# dump (référence d'intégrité pour restore.sh), rotation des KEEP derniers.
# Usage : ./backup/backup.sh          (depuis poc-resilience/, ou : just backup)
#         KEEP=14 DB_EXEC="podman exec -i resilience-alpha_db_1" ./backup/backup.sh
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")/.."
. backup/lib.sh

db=$(db_name) || die "conteneur db injoignable (la stack tourne-t-elle ?)"
stamp=$(date +%Y%m%d-%H%M%S)
base="$DUMP_DIR/$db-$stamp"
tmp="/tmp/backup-$stamp.dump"
mkdir -p "$DUMP_DIR"
trap 'dbsh "rm -f $tmp" || true' EXIT

echo "Sauvegarde de la base $db -> $base.dump"
t0=$(now_ms)
# Transaction REPEATABLE READ : son snapshot est exporté vers pg_dump, puis les
# comptages tournent dans cette même transaction. Dump et comptes voient les
# mêmes données, même si le trafic de démo continue d'écrire pendant ce temps.
dbsql > "$base.counts" <<SQL
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT pg_export_snapshot() AS snap \gset
\setenv SNAP :snap
\! pg_dump -Fc -U "\$POSTGRES_USER" -d "\$POSTGRES_DB" --snapshot="\$SNAP" -f $tmp
$COUNTS_SQL
COMMIT;
SQL

# psql ne remonte pas l'échec d'un \! : on valide le dump avant de le garder
dbsh "pg_restore -l $tmp > /dev/null" || { rm -f "$base.counts"; die "dump invalide"; }
dbsh "cat $tmp" > "$base.dump"
t1=$(now_ms)

( cd "$DUMP_DIR" && sha256sum "$(basename "$base.dump")" > "$(basename "$base.dump").sha256" )

echo "  taille        $(wc -c < "$base.dump") octets"
echo "  sha256        $(cut -d' ' -f1 "$base.dump.sha256")"
echo "  transactions  $(count_of public.transactions "$base.counts")"
echo "  durée         $((t1 - t0)) ms"

# Rotation : on garde les KEEP derniers dumps, avec leur empreinte et leurs comptes
ls -1 "$DUMP_DIR"/"$db"-*.dump | sort -r | tail -n +"$((KEEP + 1))" | while read -r old; do
  rm -f "$old" "$old.sha256" "${old%.dump}.counts"
  echo "  rotation      $(basename "$old") supprimé"
done
echo "OK, $(ls -1 "$DUMP_DIR"/"$db"-*.dump | wc -l | tr -d ' ') sauvegarde(s) conservée(s) (KEEP=$KEEP)"
