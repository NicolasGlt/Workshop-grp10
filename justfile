# Commandes du projet RESILIENCE-ALPHA. `just` seul liste les recettes.
# Installer just : Windows `winget install Casey.Just`, Linux paquet `just` ou `cargo install just`.

set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

# Moteur compose, surchargeable : just compose="podman-compose -f compose.podman.yaml" up
compose := "docker compose"

# Liste les recettes
default:
    @just --list --unsorted

# ---------------------------------------------------------------- mise en place

# Crée les .env depuis les modèles (sans écraser), à compléter ensuite
[unix]
env:
    test -f poc-resilience/.env || cp poc-resilience/.env.example poc-resilience/.env
    test -f auth-faciale/.env || cp auth-faciale/.env.example auth-faciale/.env
    @echo "Remplacer toutes les valeurs change-me, BACKOFFICE_DB_PASSWORD identique dans les deux .env"

# Crée les .env depuis les modèles (sans écraser), à compléter ensuite
[windows]
env:
    if (-not (Test-Path poc-resilience/.env)) { Copy-Item poc-resilience/.env.example poc-resilience/.env }
    if (-not (Test-Path auth-faciale/.env)) { Copy-Item auth-faciale/.env.example auth-faciale/.env }
    Write-Host "Remplacer toutes les valeurs change-me, BACKOFFICE_DB_PASSWORD identique dans les deux .env"

# ---------------------------------------------------------------- SI (poc-resilience)

# Construit et démarre toute la stack
[working-directory('poc-resilience')]
up:
    {{ compose }} up -d --build

# Arrête la stack (données conservées)
[working-directory('poc-resilience')]
down:
    {{ compose }} down

# État des conteneurs
[working-directory('poc-resilience')]
ps:
    {{ compose }} ps

# Logs en continu, d'un ou plusieurs services (tous par défaut)
[working-directory('poc-resilience')]
logs *services:
    {{ compose }} logs -f --tail 50 {{ services }}

# Rejoue les scripts d'init idempotents sur une base existante (rôle backoffice, clé marchand)
[working-directory('poc-resilience')]
db-init:
    {{ compose }} exec db sh /docker-entrypoint-initdb.d/05-backoffice.sh
    {{ compose }} exec db sh /docker-entrypoint-initdb.d/06-merchant-key.sh

# Remise à zéro complète : supprime la base, les métriques et les logs
[confirm("Supprimer tous les volumes (base, métriques, logs) ?")]
[working-directory('poc-resilience')]
reset:
    {{ compose }} down -v

# ---------------------------------------------------------------- recette

# Smoke test : paiement, WAF, observabilité
[unix]
[working-directory('poc-resilience')]
smoke:
    ./scripts/smoke-test.sh

# Smoke test : paiement, WAF, observabilité (bash de Git for Windows)
[windows]
[working-directory('poc-resilience')]
smoke:
    & "$env:ProgramFiles\Git\bin\bash.exe" scripts/smoke-test.sh

# Démo de reprise autonome : paiement, flood, détection, blocage, paiement
[unix]
[working-directory('poc-resilience')]
demo:
    ./scripts/demo-incident.sh

# Démo de reprise autonome : paiement, flood, détection, blocage, paiement
[windows]
[working-directory('poc-resilience')]
demo:
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/demo-incident.ps1

# Prépare la démo : démarre la stack, attend conteneurs sains et détecteur entraîné, puis les URL
[unix]
[working-directory('poc-resilience')]
demo-prep: up
    #!/usr/bin/env bash
    set -uo pipefail
    PROM="${PROM:-http://localhost:9090}"
    attendus=$({{ compose }} config --services | wc -l)
    for i in $(seq 1 60); do
      etat=$({{ compose }} ps 2>/dev/null)
      up=$(grep -c " Up " <<<"$etat")
      if [ "$up" -ge "$attendus" ] && ! grep -Eq "starting|unhealthy|Restarting|Created" <<<"$etat"; then ok=1; break; fi
      echo "  conteneurs : $up/$attendus démarrés, attente des healthchecks..."; sleep 5
    done
    [ "${ok:-0}" = 1 ] || { {{ compose }} ps; echo "ÉCHEC : conteneurs pas tous sains après 5 min"; exit 1; }
    echo "Conteneurs : $attendus/$attendus sains"
    entraine(){ curl -s "$PROM/api/v1/query?query=ml_detector_trained" | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(r[0]['value'][1] if r else 0)" 2>/dev/null; }
    for i in $(seq 1 36); do
      [ "$(entraine)" = 1 ] && break
      echo "  ml-detector en apprentissage de la normale (~2 min)..."; sleep 10
    done
    [ "$(entraine)" = 1 ] || { echo "ÉCHEC : ml_detector_trained != 1 après 6 min, voir just logs ml-detector"; exit 1; }
    echo "Détecteur entraîné : prêt pour just demo"
    "{{ just_executable() }}" --justfile "{{ justfile() }}" urls

# Prépare la démo : démarre la stack, attend conteneurs sains et détecteur entraîné, puis les URL
[windows]
[working-directory('poc-resilience')]
[script("powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File")]
[extension(".ps1")]
demo-prep: up
    $prom = if ($env:PROM) { $env:PROM } else { "http://localhost:9090" }
    $attendus = @({{ compose }} config --services).Count
    $ok = $false
    for ($i = 0; $i -lt 60; $i++) {
      $etat = ({{ compose }} ps 2>$null) -join "`n"
      $up = ([regex]::Matches($etat, " Up ")).Count
      if ($up -ge $attendus -and $etat -cnotmatch "starting|unhealthy|Restarting|Created") { $ok = $true; break }
      Write-Host "  conteneurs : $up/$attendus demarres, attente des healthchecks..."; Start-Sleep -Seconds 5
    }
    if (-not $ok) { {{ compose }} ps; Write-Host "ECHEC : conteneurs pas tous sains apres 5 min" -ForegroundColor Red; exit 1 }
    Write-Host "Conteneurs : $attendus/$attendus sains"
    function Entraine { try { (Invoke-RestMethod "$prom/api/v1/query?query=ml_detector_trained").data.result[0].value[1] -eq "1" } catch { $false } }
    for ($i = 0; $i -lt 36 -and -not (Entraine); $i++) { Write-Host "  ml-detector en apprentissage de la normale (~2 min)..."; Start-Sleep -Seconds 10 }
    if (-not (Entraine)) { Write-Host "ECHEC : ml_detector_trained != 1 apres 6 min, voir just logs ml-detector" -ForegroundColor Red; exit 1 }
    Write-Host "Detecteur entraine : pret pour just demo" -ForegroundColor Green
    & "{{ just_executable() }}" --justfile "{{ justfile() }}" urls

# ---------------------------------------------------------------- Red Team (attacker)
# Exercice pédagogique, laboratoire fermé, SI FICTIF du groupe, point d'accès isolé
# RESILIENCE-G10 (192.168.137.0/24). Détails et périmètre : attacker/README.md.

# Vérifie AVANT l'attaque : réseau 192.168.137.0/24, cible joignable, image hey
[unix]
attack-check target="http://192.168.137.1":
    ./attacker/preflight.sh {{ quote(target) }}

# Vérifie AVANT l'attaque : réseau 192.168.137.0/24, cible joignable, image hey
[windows]
attack-check target="http://192.168.137.1":
    & "$env:ProgramFiles\Git\bin\bash.exe" attacker/preflight.sh "{{ target }}"

# Flood HTTP du point d'entrée (WAF) depuis le PC Attaquant, via Podman rootless
[unix]
attack target="http://192.168.137.1" duration="60s" concurrency="90":
    podman run --rm docker.io/williamyeh/hey -z {{ duration }} -c {{ concurrency }} -T application/json -H "User-Agent: Mozilla/5.0" -H "Accept: application/json" "{{ target }}/api/ping"

# Flood HTTP du point d'entrée (WAF) depuis le PC Attaquant, via Podman rootless
[windows]
attack target="http://192.168.137.1" duration="60s" concurrency="90":
    podman run --rm docker.io/williamyeh/hey -z {{ duration }} -c {{ concurrency }} -T application/json -H "User-Agent: Mozilla/5.0" -H "Accept: application/json" "{{ target }}/api/ping"

# ---------------------------------------------------------------- back-office (auth-faciale)

# Installe l'environnement Python du back-office
[unix]
[working-directory('auth-faciale')]
backoffice-install:
    if command -v uv >/dev/null; then uv venv -q .venv && uv pip install -q -p .venv -r requirements.txt; else python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt; fi

# Installe l'environnement Python du back-office
[windows]
[working-directory('auth-faciale')]
backoffice-install:
    py -3.12 -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt

# Lance le back-office sur http://127.0.0.1:8000 (la stack doit tourner)
[unix]
[working-directory('auth-faciale')]
backoffice:
    .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Lance le back-office sur http://127.0.0.1:8000 (la stack doit tourner)
[windows]
[working-directory('auth-faciale')]
backoffice:
    .venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Crée un compte et enrôle son visage (back-office arrêté : la webcam ne sert qu'à un programme)
[unix]
[working-directory('auth-faciale')]
user name role="lecteur":
    .venv/bin/python scripts/create_user.py {{ name }} --role {{ role }}

# Crée un compte et enrôle son visage (back-office arrêté : la webcam ne sert qu'à un programme)
[windows]
[working-directory('auth-faciale')]
user name role="lecteur":
    .venv\Scripts\python scripts\create_user.py {{ name }} --role {{ role }}

# ---------------------------------------------------------------- aide

# Adresses des interfaces
urls:
    @echo "Boutique          http://localhost:8082"
    @echo "NovaPay           http://localhost:8083"
    @echo "API Comptes       http://localhost:8081/docs"
    @echo "Facade PayPoc     http://localhost (derrière le WAF)"
    @echo "Back-office       http://127.0.0.1:8000"
    @echo "Grafana           http://localhost:3000"
    @echo "Prometheus        http://localhost:9090"
    @echo "pgAdmin           http://localhost:5050"

# ---------------------------------------------------------------- résilience des données (PRA)

# Sauvegarde la base : dump horodaté, empreinte SHA-256, comptes de lignes, rotation des 7 derniers
[unix]
[working-directory('poc-resilience')]
backup:
    COMPOSE="{{ compose }}" ./backup/backup.sh

# Sauvegarde la base : dump horodaté, empreinte SHA-256, comptes de lignes, rotation des 7 derniers
[windows]
[working-directory('poc-resilience')]
backup:
    $env:COMPOSE = "{{ compose }}"; & "$env:ProgramFiles\Git\bin\bash.exe" backup/backup.sh

# Remplace la base par un dump (le dernier par défaut, chemin relatif à poc-resilience/), RTO mesuré
[confirm("Remplacer la base payments par le dump ? Les écritures postérieures seront perdues")]
[unix]
[working-directory('poc-resilience')]
restore file="":
    COMPOSE="{{ compose }}" ./backup/restore.sh {{ quote(file) }}

# Remplace la base par un dump (le dernier par défaut, chemin relatif à poc-resilience/), RTO mesuré
[confirm("Remplacer la base payments par le dump ? Les écritures postérieures seront perdues")]
[windows]
[working-directory('poc-resilience')]
restore file="":
    $env:COMPOSE = "{{ compose }}"; & "$env:ProgramFiles\Git\bin\bash.exe" backup/restore.sh "{{ file }}"

# Restaure un dump dans payments_restore_test, compare les comptes, sans toucher à la prod
[unix]
[working-directory('poc-resilience')]
restore-check file="":
    COMPOSE="{{ compose }}" ./backup/restore.sh --check {{ quote(file) }}

# Restaure un dump dans payments_restore_test, compare les comptes, sans toucher à la prod
[windows]
[working-directory('poc-resilience')]
restore-check file="":
    $env:COMPOSE = "{{ compose }}"; & "$env:ProgramFiles\Git\bin\bash.exe" backup/restore.sh --check "{{ file }}"

# ---------------------------------------------------------------- secrets (SOPS + age)

secrets_file := "poc-resilience/secrets/poc-resilience.enc.env"

# Crée sa clé age personnelle hors dépôt (sans écraser) et affiche la clé publique à ajouter à .sops.yaml
[unix]
secrets-keygen:
    #!/usr/bin/env bash
    set -euo pipefail
    f="${SOPS_AGE_KEY_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/sops/age/keys.txt}"
    if [ ! -f "$f" ]; then mkdir -p "$(dirname "$f")" && age-keygen -o "$f" 2>/dev/null && chmod 600 "$f"; fi
    echo "Clé privée : $f (ne jamais la copier dans le dépôt)"
    echo "Clé publique à ajouter dans .sops.yaml :"
    age-keygen -y "$f"

# Crée sa clé age personnelle hors dépôt (sans écraser) et affiche la clé publique à ajouter à .sops.yaml
[windows]
secrets-keygen:
    $f = if ($env:SOPS_AGE_KEY_FILE) { $env:SOPS_AGE_KEY_FILE } else { "$env:APPDATA\sops\age\keys.txt" }; if (-not (Test-Path $f)) { New-Item -ItemType Directory -Force (Split-Path $f) | Out-Null; age-keygen -o $f 2>$null }; Write-Host "Clé privée : $f (ne jamais la copier dans le dépôt)"; Write-Host "Clé publique à ajouter dans .sops.yaml :"; age-keygen -y $f

# Chiffre poc-resilience/.env vers le fichier SOPS versionné
[unix]
secrets-encrypt: _sops-ready
    sops encrypt --input-type dotenv --output-type dotenv --filename-override {{ secrets_file }} --output {{ secrets_file }} poc-resilience/.env
    @echo "Chiffré : {{ secrets_file }} (à commiter ; le .env en clair reste ignoré)"

# Chiffre poc-resilience/.env vers le fichier SOPS versionné
[windows]
secrets-encrypt: _sops-ready
    sops encrypt --input-type dotenv --output-type dotenv --filename-override {{ secrets_file }} --output {{ secrets_file }} poc-resilience/.env
    Write-Host "Chiffré : {{ secrets_file }} (à commiter ; le .env en clair reste ignoré)"

# Régénère poc-resilience/.env depuis le fichier SOPS (clé age privée requise)
[confirm("Écraser poc-resilience/.env par la version déchiffrée ?")]
secrets-decrypt:
    sops decrypt --input-type dotenv --output-type dotenv --output poc-resilience/.env {{ secrets_file }}

# Édite les secrets chiffrés directement (déchiffrés le temps de l'éditeur seulement)
secrets-edit: _sops-ready
    sops edit {{ secrets_file }}

# Rechiffre la clé de données pour les clés publiques actuelles de .sops.yaml (après ajout ou départ d'un membre)
secrets-updatekeys: _sops-ready
    sops updatekeys --yes {{ secrets_file }}

# Refuse de chiffrer tant que .sops.yaml porte la clé d'exemple
[private]
[unix]
_sops-ready:
    @! grep -q A-REMPLACER .sops.yaml || { echo "ERREUR : remplacer la clé d'exemple de .sops.yaml (voir poc-resilience/secrets/README.md)" >&2; exit 1; }

# Refuse de chiffrer tant que .sops.yaml porte la clé d'exemple
[private]
[windows]
_sops-ready:
    @if (Select-String -Quiet -Pattern A-REMPLACER -Path .sops.yaml) { Write-Error "remplacer la clé d'exemple de .sops.yaml (voir poc-resilience/secrets/README.md)"; exit 1 }
