#!/usr/bin/env bash
# Red Team RESILIENCE-ALPHA — flood HTTP du point d'entrée (WAF) depuis le PC Attaquant.
#
# Déclenche le scénario SO7 (déni de service par saturation) qui fait réagir la boucle
# détection ML -> remédiation Ansible du groupe. Exercice pédagogique, laboratoire
# fermé, SI FICTIF du groupe, point d'accès isolé RESILIENCE-G10 (192.168.137.0/24).
#
# Pas de sudo, pas d'installation native : l'outil `hey` tourne dans un conteneur
# public (williamyeh/hey) via Podman rootless, avec repli Docker.
#
# Usage : ./flood.sh [CIBLE] [DUREE] [CONCURRENCE]
#   CIBLE        URL du point d'entrée      (défaut http://192.168.137.1)
#   DUREE        durée du flood (format hey) (défaut 60s)
#   CONCURRENCE  connexions simultanées      (défaut 90)
#
# GARDE-FOU : refuse toute cible hors 192.168.137.0/24 ou localhost, pour ne jamais
# envoyer de charge en dehors du périmètre du laboratoire.
set -uo pipefail

TARGET="${1:-http://192.168.137.1}"
DURATION="${2:-60s}"
CONCURRENCY="${3:-90}"
PATH_ENDPOINT="/api/ping"

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

case "${1:-}" in -h|--help|help) usage 0 ;; esac

# --- Extraction de l'hôte depuis l'URL (sans scheme, sans port, sans chemin) ------
host_from_url() {
  local url="$1"
  url="${url#*://}"      # retire http:// ou https://
  url="${url%%/*}"       # retire /chemin
  url="${url%%\?*}"      # retire ?query
  url="${url##*@}"       # retire user:pass@
  url="${url%%:*}"       # retire :port
  printf '%s' "$url"
}

# --- Garde-fou de périmètre --------------------------------------------------------
in_perimeter() {
  local host="$1"
  case "$host" in
    localhost|127.0.0.1|::1) return 0 ;;
    192.168.137.*)
      # Vérifie que le dernier octet est un entier 0-255 (évite 192.168.1370 etc.)
      local last="${host##*.}"
      case "$last" in
        ''|*[!0-9]*) return 1 ;;
        *) [ "$last" -le 255 ] && return 0 || return 1 ;;
      esac
      ;;
    *) return 1 ;;
  esac
}

HOST="$(host_from_url "$TARGET")"
if [ -z "$HOST" ]; then
  echo "ERREUR : cible invalide : '$TARGET'" >&2
  usage 1
fi
if ! in_perimeter "$HOST"; then
  echo "REFUS (garde-fou de périmètre) : '$HOST' n'est pas dans 192.168.137.0/24 ni localhost." >&2
  echo "Cet outil ne vise QUE le démonstrateur du groupe sur le point d'accès RESILIENCE-G10." >&2
  exit 2
fi

# --- Moteur de conteneur : Podman d'abord, repli Docker ----------------------------
ENGINE="${ENGINE:-}"
if [ -z "$ENGINE" ]; then
  if command -v podman >/dev/null 2>&1; then ENGINE="podman"
  elif command -v docker >/dev/null 2>&1; then ENGINE="docker"
  else
    echo "ERREUR : ni podman ni docker trouvés. Installer Podman (rootless)." >&2
    exit 3
  fi
fi

URL="${TARGET%/}$PATH_ENDPOINT"
echo "=== Flood SO7 (laboratoire fermé, SI fictif du groupe)"
echo "    moteur      : $ENGINE"
echo "    cible       : $URL"
echo "    durée       : $DURATION   concurrence : $CONCURRENCY"
echo "    observation : Grafana « 07 · Résilience » + just logs ml-detector remediation"
echo

exec "$ENGINE" run --rm docker.io/williamyeh/hey \
  -z "$DURATION" -c "$CONCURRENCY" -T application/json \
  -H "User-Agent: Mozilla/5.0" -H "Accept: application/json" \
  "$URL"
