#!/usr/bin/env bash
# =====================================================================
# Restauration chronométrée d'un dump de backup.sh, avec contrôle d'intégrité :
# empreinte SHA-256, puis comptes de lignes restaurés comparés à ceux du dump.
#
#   ./backup/restore.sh [fichier.dump]          remplace la base de prod (DESTRUCTIF)
#   ./backup/restore.sh --check [fichier.dump]  restaure dans payments_restore_test,
#                                               compare, puis supprime cette base
# Sans fichier : le dump le plus récent de backup/dumps/. KEEP_TEST=1 garde la base de test.
# La durée affichée (vérification + restauration) est le RTO technique mesuré.
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")/.."
. backup/lib.sh

check=0
if [[ "${1:-}" == "--check" ]]; then check=1; shift; fi

prod=$(db_name) || die "conteneur db injoignable (la stack tourne-t-elle ?)"
file="${1:-$(ls -1 "$DUMP_DIR"/"$prod"-*.dump 2>/dev/null | sort | tail -n 1)}"
[[ -n "$file" && -f "$file" ]] || die "aucun dump trouvé (lancer d'abord : just backup)"
ref="${file%.dump}.counts"
[[ -f "$ref" ]] || die "comptes de référence absents : $ref"

if (( check )); then
  target=payments_restore_test
  [[ "$target" != "$prod" ]] || die "la base de test porte le nom de la prod"
else
  target="$prod"
fi
tmp="/tmp/restore-$$.dump"
trap 'dbsh "rm -f $tmp" || true' EXIT

echo "Restauration de $(basename "$file") dans la base $target"
t0=$(now_ms)

# 1. Intégrité du fichier
if [[ -f "$file.sha256" ]]; then
  ( cd "$(dirname "$file")" && sha256sum -c --quiet "$(basename "$file").sha256" ) \
    || die "empreinte SHA-256 invalide, dump corrompu ou modifié"
  echo "  sha256        conforme"
else
  die "empreinte absente : $file.sha256"
fi

# 2. État avant : en prod, ce qui sera perdu depuis la sauvegarde (RPO observé)
if (( ! check )); then
  before=$(count_of public.transactions <(counts)); before=${before:-0}
  dumped=$(count_of public.transactions "$ref")
  echo "  transactions  avant : $before, dans le dump : $dumped"
  if (( before > dumped )); then
    echo "  RPO observé   $((before - dumped)) transaction(s) postérieure(s) au dump seront perdues"
  fi
fi

# 3. Restauration
dbsh "cat > $tmp" < "$file"
if (( check )); then
  printf 'SET client_min_messages = warning;\nDROP DATABASE IF EXISTS %s WITH (FORCE);\nCREATE DATABASE %s;\n' "$target" "$target" | dbsql postgres
  dbsh "pg_restore --exit-on-error -U \"\$POSTGRES_USER\" -d $target $tmp"
else
  # La base est recréée de zéro : DROP ... WITH (FORCE) coupe les sessions des
  # services (ils se reconnectent), puis --create rejoue la base, ses droits et son schéma.
  printf 'SET client_min_messages = warning;\nDROP DATABASE IF EXISTS "%s" WITH (FORCE);\n' "$target" | dbsql postgres
  dbsh "pg_restore --exit-on-error --create -U \"\$POSTGRES_USER\" -d postgres $tmp"
fi
t1=$(now_ms)

# 4. Intégrité des données : chaque table doit avoir le nombre de lignes du dump
got=$(counts "$target")
if diff <(printf '%s\n' "$got") "$ref" > /dev/null; then
  echo "  comptes       $(wc -l < "$ref" | tr -d ' ') tables identiques au dump"
  echo "  transactions  après : $(count_of public.transactions "$ref")"
  status=0
else
  echo "  comptes       ÉCART avec le dump (restauré <  > attendu) :"
  diff <(printf '%s\n' "$got") "$ref" | sed 's/^/    /' || true
  status=1
fi

if (( check )) && [[ "${KEEP_TEST:-0}" != 1 ]]; then
  printf 'SET client_min_messages = warning;\nDROP DATABASE IF EXISTS %s WITH (FORCE);\n' "$target" | dbsql postgres
  echo "  base de test  supprimée"
fi

echo "RTO mesuré : $(( (t1 - t0) / 1000 )).$(printf '%03d' $(( (t1 - t0) % 1000 ))) s (vérification + restauration)"
exit "$status"
