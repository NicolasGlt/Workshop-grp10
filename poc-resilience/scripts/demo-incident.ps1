# =====================================================================
# Démo de reprise autonome (PowerShell / Windows)
#   1. service AVANT (paiement OK)
#   2. incident (flood HTTP -> l'API sature)
#   3. ml-detector détecte -> remediation agit (SANS humain)
#   4. service APRÈS (nouveau paiement OK)
# Pré-requis : la stack tourne et le ml-detector est "actif" (modèle entraîné).
# =====================================================================
$ErrorActionPreference = "SilentlyContinue"
# Paiement comme un vrai client : achat sur la boutique, qui appelle PayPoc via le WAF.
# Ne dépend pas de l'IP vue par le WAF (sous Docker Desktop, l'hôte et le PC Attaquant
# peuvent arriver avec la même IP de passerelle : un paiement direct serait bloqué aussi).
function Pay {
  $body = @{
    items = @(@{ id = "bra-cerrado"; qty = 1; weight = "250g" })
    customer = @{ name = "Demo"; email = "demo@poc.local"; address = "1 rue du Test"; zip = "75001"; city = "Paris" }
    card = @{ number = "5555555555554444"; exp_month = 12; exp_year = 30; cvv = "123"; holder = "DEMO USER" }
  } | ConvertTo-Json -Depth 4
  try { (Invoke-RestMethod -Method Post http://localhost:8082/api/checkout -ContentType 'application/json' -Body $body).status }
  catch { "erreur" }
}

Write-Host "`n=== 1. État AVANT incident ===" -ForegroundColor Cyan
# Le détecteur doit avoir appris la normale (~2 min après son démarrage), sinon la démo ne prouve rien.
function Trained { ((Invoke-RestMethod "http://localhost:9090/api/v1/query?query=ml_detector_trained").data.result[0].value[1]) -eq "1" }
for ($i = 0; $i -lt 30 -and -not (Trained); $i++) { Write-Host "  détecteur en apprentissage..."; Start-Sleep -Seconds 10 }
if (-not (Trained)) { Write-Host "ÉCHEC : détecteur non entraîné, démo annulée" -ForegroundColor Red; exit 1 }
Write-Host "Détecteur entraîné : oui"
Write-Host ("Paiement de contrôle : " + (Pay)) -ForegroundColor Green

Write-Host "`n=== 2. Déclenchement de l'incident (flood HTTP) ===" -ForegroundColor Yellow
Write-Host "Ouvre Grafana -> 07 - Résilience pour regarder en direct."
docker run --rm --network resilience-alpha_edge williamyeh/hey -z 60s -c 90 -T application/json `
  -H "User-Agent: Mozilla/5.0" -H "Accept: application/json" `
  http://waf:8080/api/ping | Select-String "Requests/sec|Status code"

Write-Host "`n=== 3. Reprise autonome en cours (détection -> remédiation) ===" -ForegroundColor Yellow
Write-Host "Suivi : docker compose logs -f ml-detector remediation"
Start-Sleep -Seconds 25
Write-Host "Remédiations déclenchées :"
(Invoke-WebRequest "http://localhost:9090/api/v1/query?query=ml_detector_remediations_total" -UseBasicParsing).Content

Write-Host "`n=== 4. État APRÈS remédiation ===" -ForegroundColor Cyan
Start-Sleep -Seconds 10
Write-Host ("Nouveau paiement : " + (Pay)) -ForegroundColor Green
Write-Host "`nSi le paiement est 'approved', le service a été rétabli automatiquement." -ForegroundColor Green
