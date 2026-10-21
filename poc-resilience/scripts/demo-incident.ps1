# =====================================================================
# Démo de reprise autonome (PowerShell / Windows)
#   1. service AVANT (paiement OK)
#   2. incident (flood HTTP -> l'API sature)
#   3. ml-detector détecte -> remediation agit (SANS humain)
#   4. service APRÈS (nouveau paiement OK)
# Pré-requis : la stack tourne et le ml-detector est "actif" (modèle entraîné).
# =====================================================================
$ErrorActionPreference = "SilentlyContinue"
$KEY = "pk_nova_demo_bYtR7xQ2"

function Pay {
  $body = @{
    amount = "12.50"; currency = "EUR"; order_ref = "DEMO"
    customer_name = "Demo"; customer_email = "demo@poc.local"
    card = @{ number = "4242424242424242"; exp_month = 12; exp_year = 30; cvv = "123"; holder = "DEMO USER" }
  } | ConvertTo-Json
  (Invoke-RestMethod -Method Post http://localhost/api/charge -Headers @{ "X-Api-Key" = $KEY } `
    -ContentType 'application/json' -Body $body).status
}

Write-Host "`n=== 1. État AVANT incident ===" -ForegroundColor Cyan
Write-Host ("Détecteur entraîné (1=oui) : ") -NoNewline
(Invoke-WebRequest "http://localhost:9090/api/v1/query?query=ml_detector_trained" -UseBasicParsing).Content
Write-Host ("Paiement de contrôle : " + (Pay)) -ForegroundColor Green

Write-Host "`n=== 2. Déclenchement de l'incident (flood HTTP) ===" -ForegroundColor Yellow
Write-Host "Ouvre Grafana -> 07 - Résilience pour regarder en direct."
docker run --rm --network resilience-alpha_edge williamyeh/hey -n 9000 -c 90 `
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
