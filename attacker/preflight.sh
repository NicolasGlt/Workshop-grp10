#!/usr/bin/env bash
# Red Team RESILIENCE-ALPHA — vérifications AVANT de lancer le flood.
#
# Contrôle, sans rien attaquer :
#   1. le poste est bien sur le réseau 192.168.137.0/24 (point d'accès RESILIENCE-G10) ;
#   2. la cible (le WAF) répond ;
#   3. l'image `hey` est disponible (sinon indique comment la télécharger).
#
# Usage : ./preflight.sh [CIBLE]   (défaut http://192.168.137.1)
set -uo pipefail

TARGET="${1:-http://192.168.137.1}"
PATH_ENDPOINT="/api/ping"
rc=0

host_from_url() {
  local url="$1"
  url="${url#*://}"; url="${url%%/*}"; url="${url%%\?*}"; url="${url##*@}"; url="${url%%:*}"
  printf '%s' "$url"
}

echo "=== Préflight Red Team (laboratoire fermé, SI fictif du groupe)"
echo "    cible : $TARGET"
echo

# --- 1. Réseau : une IP locale dans 192.168.137.0/24 ------------------------------
echo "[1/3] Réseau 192.168.137.0/24 (point d'accès RESILIENCE-G10)"
ips=""
if command -v ip >/dev/null 2>&1; then
  ips="$(ip -4 -o addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1)"
elif command -v ipconfig >/dev/null 2>&1; then
  ips="$(ipconfig 2>/dev/null | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}')"   # Git Bash sous Windows
elif command -v hostname >/dev/null 2>&1; then
  ips="$(hostname -I 2>/dev/null)"
fi
if printf '%s\n' $ips | grep -q '^192\.168\.137\.'; then
  echo "      OK : $(printf '%s\n' $ips | grep '^192\.168\.137\.' | tr '\n' ' ')"
else
  echo "      ÉCHEC : aucune IP dans 192.168.137.0/24 (es-tu connecté à RESILIENCE-G10 ?)" >&2
  rc=1
fi

# --- 2. La cible répond -----------------------------------------------------------
echo "[2/3] Cible joignable : ${TARGET%/}$PATH_ENDPOINT"
if command -v curl >/dev/null 2>&1; then
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "${TARGET%/}$PATH_ENDPOINT" 2>/dev/null || echo 000)"
  if [ "$code" != "000" ]; then
    echo "      OK : réponse HTTP $code"
  else
    echo "      ÉCHEC : pas de réponse (POC démarré côté Hôte ? bon port ?)" >&2
    rc=1
  fi
else
  echo "      IGNORÉ : curl absent" >&2
fi

# --- 3. Image hey disponible ------------------------------------------------------
echo "[3/3] Image williamyeh/hey disponible"
ENGINE="${ENGINE:-}"
if [ -z "$ENGINE" ]; then
  if command -v podman >/dev/null 2>&1; then ENGINE="podman"
  elif command -v docker >/dev/null 2>&1; then ENGINE="docker"; fi
fi
if [ -z "$ENGINE" ]; then
  echo "      ÉCHEC : ni podman ni docker trouvés" >&2
  rc=1
elif "$ENGINE" image exists docker.io/williamyeh/hey 2>/dev/null \
     || "$ENGINE" images 2>/dev/null | grep -q 'williamyeh/hey'; then
  echo "      OK : image présente ($ENGINE)"
else
  echo "      ABSENTE : lancer '$ENGINE pull docker.io/williamyeh/hey' (sinon téléchargée au 1er flood)"
fi

echo
if [ "$rc" -eq 0 ]; then
  echo "Préflight OK : prêt pour 'just attack' / 'bash attacker/flood.sh'."
else
  echo "Préflight : au moins une vérification a échoué (voir ci-dessus)." >&2
fi
exit "$rc"
