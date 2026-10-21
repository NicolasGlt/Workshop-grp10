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
      if ($up -ge $attendus -and $etat -notmatch "starting|unhealthy|Restarting|Created") { $ok = $true; break }
      Write-Host "  conteneurs : $up/$attendus demarres, attente des healthchecks..."; Start-Sleep -Seconds 5
    }
    if (-not $ok) { {{ compose }} ps; Write-Host "ECHEC : conteneurs pas tous sains apres 5 min" -ForegroundColor Red; exit 1 }
    Write-Host "Conteneurs : $attendus/$attendus sains"
    function Entraine { try { (Invoke-RestMethod "$prom/api/v1/query?query=ml_detector_trained").data.result[0].value[1] -eq "1" } catch { $false } }
    for ($i = 0; $i -lt 36 -and -not (Entraine); $i++) { Write-Host "  ml-detector en apprentissage de la normale (~2 min)..."; Start-Sleep -Seconds 10 }
    if (-not (Entraine)) { Write-Host "ECHEC : ml_detector_trained != 1 apres 6 min, voir just logs ml-detector" -ForegroundColor Red; exit 1 }
    Write-Host "Detecteur entraine : pret pour just demo" -ForegroundColor Green
    & "{{ just_executable() }}" --justfile "{{ justfile() }}" urls

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
