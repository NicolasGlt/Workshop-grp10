# POC Resilience-Alpha — PayPoc

Passerelle de paiement en Docker Compose. Une **boutique de café fictive** (Brûlerie du Comptoir) encaisse via **PayPoc** ; le client saisit sa carte au paiement, PayPoc valide et interroge une **banque fictive** (cartes de test) qui autorise ou refuse. Le tout derrière un WAF, avec métriques et logs centralisés. **Aucune donnée bancaire réelle.**

## Flux de paiement

```
   ┌────────────┐   panier + carte   ┌────────────┐   POST /charge (clé API)   ┌──────────┐
   │  Client    │ ─────────────────► │  Boutique  │ ─────────────────────────► │  PayPoc  │
   │(navigateur)│                    │ (merchant) │ ◄───────────────────────── │  (api)   │
   └────────────┘                    └────────────┘   résultat approved/declined└────┬─────┘
                                      café :8082        via waf → frontend → api      │ autorise ?
                                                                                      ▼
                                                                                ┌──────────┐
                                                                                │  Banque  │
                                                                                │  (bank)  │
                                                                                └──────────┘
```

Le client saisit ses coordonnées et sa carte sur la boutique. Le marchand transmet la carte à PayPoc (serveur-à-serveur, via le WAF). PayPoc **valide** (Luhn, CVV, date), **tokenise**, demande l'autorisation à la banque, enregistre le paiement et renvoie le résultat — que la boutique affiche. L'appel PayPoc passe par le WAF (`merchant → waf → frontend → api`).

## Composants

| Service | Rôle | Exposé |
|---|---|---|
| `waf` | nginx + ModSecurity/CRS, point d'entrée de l'API PayPoc | **:80** |
| `frontend` | nginx : façade + reverse-proxy `/api` + blocklist (résilience) | via WAF |
| `api` | PayPoc : passerelle (clé API marchand, validation carte, tokenisation) | via WAF |
| `bank` | Banque fictive : décision par cartes de test | interne |
| `merchant` | Brûlerie du Comptoir : boutique café + **machines** (catalogue, panier, checkout carte) ; **comptes clients** : inscription/connexion, historique commandes, cartes enregistrées | **:8082** |
| `accounts-api` | API Comptes/Cartes (**travail BDD du groupe**) : comptes, cartes tokenisées, vérif. mot de passe | **:8081** (`/docs`) |
| `clientapp` | **NovaPay** : espace client (néobanque) — Alice/Bob consultent solde, cartes, opérations (lecture seule) | **:8083** |
| `db` | PostgreSQL — **schéma bancaire du groupe** (utilisateurs, comptes, comptes_bancaires, cartes, transactions, logs) + table `merchants` de la passerelle | interne |
| `pgadmin` | Console d'admin de la base (serveur pré-enregistré) | **:5050** |
| `ml-detector` | Détection d'anomalies (Isolation Forest) → déclenche la remédiation | interne |
| `remediation` | Moteur de remédiation : playbooks Ansible (block_ip, restart) | interne |
| `prometheus` + exporters | métriques | :9090 (local) |
| `loki` + `alloy` | logs de tous les conteneurs | interne |
| `grafana` | dashboards | **:3000** |

Réseaux : `edge` (waf, frontend, merchant) seul exposé ; `app` et `data` internes (la BDD et la banque ne sont jamais publiées) ; `monitoring` pour la collecte.

## Démarrage

```bash
cp .env.example .env
# remplacer les "change-me" ; laisser MERCHANT_API_KEY tel quel (doit matcher le seed)
docker compose up -d --build        # ajouter --scale cadvisor=0 sous Docker Desktop
docker compose ps
./scripts/smoke-test.sh
```

| Interface | URL | Accès |
|---|---|---|
| Boutique Brûlerie du Comptoir | http://localhost:8082 | — (paiement invité) |
| Façade PayPoc (API derrière le WAF) | http://localhost | — |
| API Comptes/Cartes (Swagger) | http://localhost:8081/docs | — |
| **NovaPay** (espace client) | http://localhost:8083 | `alice@example.com` / `Alice_Test_2026!` · `bob@example.com` / `Bob_Test_2026!` |
| pgAdmin (console BDD) | http://localhost:5050 | `PGADMIN_EMAIL` / `PGADMIN_PASSWORD` |
| Grafana | http://localhost:3000 | `admin` / `GRAFANA_ADMIN_PASSWORD` |
| Prometheus | http://localhost:9090 | local uniquement |

### Démo guidée

1. Va sur **http://localhost:8082**, ajoute des cafés au panier, puis « Passer au paiement ».
2. Renseigne les coordonnées et la carte, puis « Payer ».
3. Confirmation à l'écran (référence commande + référence banque).
4. Ouvre Grafana → dossier *Resilience-Alpha* : paiements approuvés/refusés, décisions banque, taux d'approbation, logs.

## Cartes de test

Date d'expiration future, CVV à 3 chiffres (libre).

| Numéro | Résultat |
|---|---|
| `4242 4242 4242 4242` | approuvé |
| `4000 0000 0000 0002` | refusé — fonds insuffisants |
| `4000 0000 0000 9995` | refusé — fonds insuffisants |
| `4100 0000 0000 0019` | refusé — carte bloquée |
| `4000 0000 0000 0127` | refusé — CVV incorrect |
| tout autre numéro valide (Luhn) | approuvé |

## API PayPoc

| Méthode | Route | Auth | Rôle |
|---|---|---|---|
| POST | `/api/charge` | clé API (`X-Api-Key`) | encaisse : valide la carte, autorise, enregistre |
| GET | `/api/payments/{id}` | clé API | statut d'un paiement (reçu marchand) |
| GET | `/api/ping` | — | endpoint léger (cible des tests de charge) |

La banque (`POST /authorize`, interne) décide selon le numéro de carte de test. Sinon elle renvoie un `auth_code` + `bank_reference`.

> Sécurité : le **numéro de carte et le CVV ne sont jamais stockés ni journalisés** — seuls `card_last4`, la marque et la référence banque sont conservés dans la transaction (esprit PCI DSS). Validation Luhn/CVV/date côté passerelle avant tout appel banque. SQL paramétré, rôle BDD `app_user` sans droit DDL. Si la banque est injoignable, **rien n'est persisté** (transaction annulée) et l'API renvoie 502.

## Base de données

La base est le **modèle bancaire conçu par le groupe (partie BDD)**, adopté tel quel comme socle du projet : tables `utilisateurs`, `comptes`, `comptes_bancaires`, `cartes`, `transactions`, `logs`, et fonctions SQL (`creer_compte`, `ajouter_compte_bancaire`, `ajouter_carte`, `verify_password` — bcrypt via pgcrypto). Schéma : [`docs/schema-bdd.png`](docs/schema-bdd.png).

La passerelle PayPoc s'y branche **sans modifier ce modèle**, en ajoutant seulement la table `merchants` (identité marchand → compte bancaire d'encaissement). Un paiement par carte sur la boutique devient une ligne `transactions` du compte système **EXTERNAL-GATEWAY** (émetteur) vers le compte du marchand (récepteur) : `COMPLETED` si la banque autorise (le solde du marchand est crédité), `REJECTED` sinon. Chaque décision est tracée dans `logs`. L'`accounts-api` (travail du groupe) expose les comptes/cartes sur ce même schéma.

| Couche d'init (`db/init/`) | Contenu |
|---|---|
| `01-core.sql` | schéma + fonctions du groupe (socle de référence) |
| `02-gateway.sql` | tables `merchants` et `commandes` (ajouts passerelle, sans toucher au modèle) |
| `03-seed.sql` | compte système EXTERNAL-GATEWAY, marchand Brûlerie + clé API, jeu de démo |
| `04-roles.sh` | rôles à privilèges minimaux `app_user` / `exporter` |

### Espace client — NovaPay (`:8083`)

Néobanque de démonstration **en lecture seule** sur le même schéma. Alice ou Bob se connectent (email + mot de passe vérifiés par la fonction SQL `verify_password`, jeton JWT) et visualisent : solde de leurs comptes bancaires, cartes (seulement `card_last4`, jamais le PAN/CVV) et historique de leurs transactions. Aucune écriture, rôle `app_user`.

| Utilisateur | Identifiants |
|---|---|
| Alice | `alice@example.com` / `Alice_Test_2026!` |
| Bob | `bob@example.com` / `Bob_Test_2026!` |

## Observabilité

**Prometheus** : `payment_payments_total{status}`, `payment_amount_euros_total`, `payment_bank_calls_total{outcome}`, `bank_authorizations_total{decision,reason}`, `payment_card_validation_total{result}`, métriques HTTP, nginx, PostgreSQL, conteneurs.

**Loki** (label `service`) : `{service="api"}` événements métier JSON (`payment_approved`, `payment_declined`, `card_validation_failed`…), `{service="bank"}` décisions d'autorisation, `{service="waf"}` audit ModSecurity.

Le journal de sécurité est doublé en base dans la table `logs` du modèle bancaire.

**Sondes actives** : `blackbox-exporter` interroge les endpoints (`/health` de chaque service, `/healthz` du WAF) toutes les 10 s → `probe_success`, `probe_duration_seconds`. Pas de script à lancer.

**Dashboards Grafana** (dossier *Resilience-Alpha*), séparés par thème :

| Dashboard | Contenu |
|---|---|
| 00 · Vue d'ensemble | santé des services, trafic, erreurs, latence, taux d'approbation |
| 01 · Paiements (métier) | paiements par statut, décisions banque, motifs de refus, montants |
| 02 · API & performance | débit par endpoint, latences p50/p95/p99, erreurs 4xx/5xx |
| 03 · PostgreSQL | connexions, commits/rollbacks, deadlocks, cache hit, taille |
| 04 · Disponibilité (sondes) | `probe_success`, temps de réponse et code HTTP par endpoint |
| 05 · Sécurité & WAF | événements ModSecurity, 403, paiements refusés par IP, logs |
| 06 · Conteneurs (infra) | CPU/RAM/réseau par conteneur (cAdvisor, hôte Linux) |

**Alertes** (Grafana → Alerting → dossier *Alertes Resilience-Alpha*), provisionnées automatiquement : service down, PostgreSQL down, sonde en échec, taux de 5xx > 5 %, latence p95 > 1 s. Elles s'affichent dans l'UI d'alerting ; pour être notifié (e-mail, Slack…), configure un *contact point* dans Grafana.

## Exploitation

```bash
docker compose logs -f api bank merchant waf
docker compose exec db psql -U db_admin -d payments -c "SELECT status, count(*) FROM payments GROUP BY status;"
docker compose down            # arrêt (données conservées)
docker compose down -v         # réinitialisation complète (BDD + soldes banque)
```

> Les soldes de la banque sont en mémoire et repartent à leur valeur initiale à chaque redémarrage du conteneur `bank`.

## Dépannage

| Symptôme | Piste |
|---|---|
| `db` en boucle, `pg_admin disallowed` | le `POSTGRES_USER` ne doit pas commencer par `pg_` (ici `db_admin`) |
| `db` en boucle, `\r`/`not found` | scripts en CRLF → convertir `db/init/*` en LF, puis `down -v` |
| Paiement « Banque injoignable » | `docker compose logs bank` ; le paiement reste rejouable |
| Clé API invalide au `/buy` | `MERCHANT_API_KEY` du `.env` ≠ `api_key` du seed → réaligner, `down -v` |
| Target `cadvisor` down | normal sous Docker Desktop : `--scale cadvisor=0` |

## Boucle de résilience autonome (détection → remédiation)

Le cœur du sujet : attaque → détection → **réponse automatique sans intervention humaine** → service rétabli.

```
  métriques        anomalie          décision           action Ansible
Prometheus ─► ml-detector ─────► remediation ─────► block_ip  (deny nginx + reload)
  /Loki       Isolation Forest    (token, remnet)    restart_service (docker restart)
                                                      ▲ socket Docker (seul composant)
```

- **ml-detector** apprend la « normale » (débit, erreurs, latence) pendant ~2 min, puis score chaque mesure. Après 3 anomalies consécutives, il décide une action et appelle la remédiation. Expose `ml_detector_anomaly`, `ml_detector_anomaly_score`, `ml_detector_remediations_total`.
- **remediation** exécute les playbooks Ansible. Accès maîtrisé : réseau interne `remnet` (joignable seulement par le détecteur), token obligatoire, garde-fous (IP jamais bloquées via `SAFE_IPS`, TTL de 5 min sur les blocages, anti-boucle sur les redémarrages). C'est le **seul** composant avec accès au socket Docker.
- Deux modes selon l'environnement (variable `FLOOD_ACTION`) :
  - `restart` (défaut, **mono-poste local**) : un flood sature l'API → redémarrage du service.
  - `block_ip` (**setup 2 PC**) : l'IP de l'attaquant est identifiée (logs WAF) et bloquée au niveau du frontend → le flood tombe en 403, le service reste dispo.

### Démo de reprise (Clip Chrono)

```powershell
./scripts/demo-incident.ps1
```

Le script : montre une transaction OK (avant), déclenche le flood, laisse la boucle détecter et remédier, puis rejoue une transaction (après). À regarder en direct dans Grafana → **07 · Résilience**. Suivi des décisions :

```powershell
docker compose logs -f ml-detector remediation
```

Vérifier l'état de la boucle :

```powershell
# modèle entraîné ? (1 = actif)
curl http://localhost:9090/api/v1/query?query=ml_detector_trained
# IP actuellement bloquées (mode block_ip)
docker compose exec remediation sh -c "wget -qO- http://localhost:8000/status"
```

## Prochaines étapes

1. Assistant RAG local (Ollama + LangChain) pour les opérateurs.
2. Gestion des secrets par SOPS (en remplacement du `.env`).
3. Gouvernance : EBIOS RM, PCA/PRA, mapping NIS2/DORA.
4. Générateur de trafic légitime permanent (baseline plus riche).
5. Sauvegarde / restauration PostgreSQL (RTO/RPO).
