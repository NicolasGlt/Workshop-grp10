# PayPoc — Descriptif technique de l'architecture

POC Resilience-Alpha. Passerelle de paiement façon PayPal : un site marchand fictif encaisse via PayPoc, qui interroge une banque fictive pour autoriser ou refuser le paiement. Le tout derrière un WAF, avec métriques et logs centralisés.

---

## 1. Vue d'ensemble

```
   ┌──────────┐  panier + carte  ┌────────────┐  POST /charge (clé API, via WAF)
   │  Client  │ ───────────────► │  Boutique  │ ─────────────────────────────────┐
   │(navigateur)│                │ (merchant) │ ◄──── résultat approved/declined  │
   └──────────┘  café :8082      └────────────┘                                   ▼
                                                  ┌──────────┐  /api/*  ┌──────────┐  autorise ? ┌──────────┐
                                           :80 ──►│   WAF    │ ───────► │   api    │ ──────────► │  bank    │
                                                  │nginx+CRS │  frontend│ (PayPoc) │             │(FastAPI) │
                                                  └──────────┘  (proxy) └────┬─────┘             └──────────┘
                                                                             │ SQL
                                                                             ▼
                                                                       ┌──────────┐
                                                                       │   db     │
                                                                       └──────────┘

   Observabilité : chaque conteneur expose /metrics (scrapé par Prometheus) et logue
   en JSON sur stdout (collecté par Alloy -> Loki). Grafana lit Prometheus + Loki.
```

- Le client saisit ses coordonnées et sa carte sur la **boutique** (paiement invité, pas de compte).
- La boutique transmet la carte à **PayPoc** en serveur-à-serveur (`POST /charge`, clé API), à travers le WAF.
- PayPoc **valide** la carte (Luhn, CVV, date), **tokenise**, puis demande l'autorisation à la **banque** (décision par cartes de test).
- PayPoc enregistre le paiement (sans PAN/CVV) et renvoie le résultat, que la boutique affiche.

L'appel serveur-à-serveur du marchand vers l'API PayPoc transite par le WAF (`merchant → waf → frontend → api`).

---

## 2. Les conteneurs

| Conteneur | Image | Techno | Rôle | Port hôte |
|---|---|---|---|---|
| `waf` | `owasp/modsecurity-crs:nginx-alpine` | nginx + ModSecurity + CRS | Pare-feu applicatif (couche 7), point d'entrée PayPoc | **80** |
| `frontend` | build maison (`nginx`) | nginx | Façade + reverse-proxy `/api` + blocklist (résilience) | via WAF |
| `api` | build maison | Python / FastAPI | Passerelle de paiement PayPoc | interne (8000) |
| `bank` | build maison | Python / FastAPI | Banque fictive : autorise/refuse, détient les soldes | interne (8000) |
| `merchant` | build maison | Python / FastAPI | Brûlerie du Comptoir : boutique café (catalogue, panier, checkout carte) | **8082** |
| `db` | `postgres:16-alpine` | PostgreSQL 16 | Données (users, cartes, marchands, paiements, audit) | interne (5432) |
| `prometheus` | `prom/prometheus` | Prometheus | Collecte et stocke les métriques | 9090 (local) |
| `loki` | `grafana/loki` | Loki | Agrège les logs | interne |
| `alloy` | `grafana/alloy` | Grafana Alloy | Collecte les logs de tous les conteneurs → Loki | interne |
| `grafana` | `grafana/grafana` | Grafana | Dashboards (métriques + logs) | **3000** |
| `postgres-exporter` | `prometheuscommunity/postgres-exporter` | exporter | Expose les stats PostgreSQL à Prometheus | interne |
| `nginx-exporter` | `nginx/nginx-prometheus-exporter` | exporter | Expose les stats nginx (frontend) à Prometheus | interne |
| `cadvisor` | `gcr.io/cadvisor/cadvisor` | cAdvisor | Métriques CPU/RAM/réseau par conteneur | interne |
| `blackbox` | `prom/blackbox-exporter` | blackbox-exporter | Sondes HTTP actives (synthetic monitoring) sur les endpoints | interne |
| `ml-detector` | build maison | Python / scikit-learn (Isolation Forest) | Détecte l'anomalie et décide l'action | interne |
| `remediation` | build maison | Python / FastAPI + Ansible | Exécute la réponse automatique (playbooks) | interne |

### Détail du fonctionnement

**`waf`** — nginx compilé avec ModSecurity et le jeu de règles OWASP CRS. Il reçoit tout le trafic sur le port 80 et le relaie vers `frontend` (variable `BACKEND`). Chaque requête est scorée ; au-delà du seuil (`ANOMALY_INBOUND`), elle est bloquée en 403. Variables clés : `MODSEC_RULE_ENGINE` (On = bloque, DetectionOnly = journalise seulement), `BLOCKING_PARANOIA` (1 à 4). Les blocages sont journalisés en JSON.

**`frontend`** — nginx seul (pas de build applicatif). Deux rôles : reverse-proxy de `/api/*` vers `api:8000` (c'est le point d'entrée de l'API derrière le WAF) et application de la **blocklist** alimentée par la remédiation (`map $http_x_forwarded_for`). Expose aussi `stub_status` pour `nginx-exporter`, et sert une page de façade statique.

**`api` (PayPoc)** — cœur de la passerelle. Authentifie le marchand par **clé API** (`X-Api-Key`). Sur `POST /charge`, il **valide la carte** (Luhn, CVV, date d'expiration), génère un **token** opaque et les 4 derniers chiffres, demande l'autorisation à la banque, enregistre le paiement et journalise — **sans jamais stocker ni logger le numéro complet ou le CVV**. Expose `/ping` (cible des tests de charge) et les métriques sur `/metrics`. Requêtes SQL paramétrées, rôle `app_user` sans droit DDL.

**`bank`** — banque fictive. `POST /authorize` reçoit `{card_number, amount, currency}` et décide selon des **cartes de test déterministes** (`4242…` approuvée, `4000…0002` fonds insuffisants, `4100…0019` bloquée, etc. ; tout autre numéro valide = approuvé). Renvoie `decision`, `auth_code`, `bank_reference`. Stateless : aucun stockage, le PAN n'apparaît jamais dans les logs (seulement les 4 derniers chiffres).

**`merchant` (Brûlerie du Comptoir)** — boutique de café (SPA : catalogue détaillé, panier, checkout avec saisie carte). `GET /api/products` sert le catalogue ; `POST /api/checkout` **recalcule le total côté serveur** (jamais confiance au client), transmet la carte à PayPoc (`/charge`, via le WAF) et renvoie le résultat. La boutique ne conserve rien de la carte.

**`db`** — PostgreSQL. Les scripts de `db/init/` s'exécutent **au premier démarrage uniquement** (base vide) : création du schéma, données de démo, et rôles à privilèges minimaux (`app_user`, `exporter`).

**Chaîne d'observabilité** — `prometheus` scrape périodiquement `/metrics` de l'api, la banque, le marchand, nginx, PostgreSQL et les conteneurs. `alloy` lit les logs stdout de tous les conteneurs du projet via le socket Docker et les pousse dans `loki` (label `service` = nom du service). `grafana` est provisionné automatiquement avec les deux sources (Prometheus + Loki) et le dashboard *Resilience-Alpha*.

---

## 3. Les réseaux Docker

Le cloisonnement réseau est un pilier de la sécurité : seul `edge` est exposé, la base et la banque ne sont jamais publiées.

| Réseau | Exposé ? | Membres | Rôle |
|---|---|---|---|
| `edge` | oui (ports 80, 8082) | waf, frontend, merchant | point d'entrée public |
| `app` | interne | frontend, api, bank | l'API et la banque ne sont pas joignables de l'extérieur |
| `data` | interne | api, accounts-api, db, postgres-exporter, pgadmin | la base elle-même n'a ni port publié ni accès Internet |

> pgAdmin et `clientapp` (NovaPay) sont aussi rattachés à `monitoring` (non-interne) : un conteneur uniquement sur un réseau `internal` ne peut pas exposer de port publié, c'est ce second réseau qui permet la publication de `:5050` / `:8083`.

**Espace client NovaPay (`clientapp`, `:8083`)** — application de consultation en lecture seule sur le modèle bancaire : connexion (email + mot de passe via `verify_password`, JWT), puis affichage du solde des comptes, des cartes (`card_last4` seulement) et des transactions. Rôle `app_user`, aucune écriture.
| `monitoring` | interne (sauf 9090/3000) | prometheus, grafana, loki, alloy, exporters + api, frontend, bank, merchant | collecte métriques/logs |

Un conteneur peut appartenir à plusieurs réseaux : par exemple `api` est sur `app` (recevoir le frontend et joindre la banque), `data` (joindre la base) et `monitoring` (être scrapé). `merchant` est sur `edge` (être joignable et joindre le WAF) et `monitoring`.

---

## 4. Modèle de données (PostgreSQL)

La base reprend **le modèle bancaire conçu par le groupe (partie BDD)**, adopté tel quel comme socle. Schéma complet : [`schema-bdd.png`](schema-bdd.png).

| Table (modèle du groupe) | Contenu |
|---|---|
| `utilisateurs` | identité : prénom, nom |
| `comptes` | compte applicatif : email, `password_hash` (bcrypt), téléphone, adresse, statut |
| `comptes_bancaires` | compte bancaire : `iban_reference`, `solde` (≥ 0), devise |
| `cartes` | carte tokenisée : `card_token`, `card_last4`, hachages (numéro/nom/expiration) |
| `transactions` | mouvement : émetteur, récepteur, montant, devise, `statut`, `reference_banque`, description |
| `logs` | journal : `type_event`, `niveau`, `adresse_ip`, description |

Fonctions SQL fournies : `creer_compte`, `ajouter_compte_bancaire`, `ajouter_carte`, `hash_password` / `verify_password` (bcrypt via pgcrypto).

**Ajout de la passerelle** (sans modifier le modèle ci-dessus) :

| Table (passerelle) | Contenu |
|---|---|
| `merchants` | marchand : nom, `api_key`, `id_compte_bancaire` d'encaissement |
| `commandes` | commande boutique : référence, livraison (nom, email, adresse, CP, ville), montant, statut ; liée au marchand (`id_merchant`) et à la transaction (`id_transaction`). `id_compte` est rempli si l'acheteur était **connecté** (compte client), NULL pour un achat invité — jamais de lien vers un compte bancaire |

Un paiement carte sur la boutique devient une ligne `transactions` du compte système **EXTERNAL-GATEWAY** (émetteur) vers le compte du marchand (récepteur) : `COMPLETED` (solde marchand crédité) ou `REJECTED`. Les 4 derniers chiffres et la marque sont portés par la `description` ; **ni numéro complet, ni CVV**. Chaque décision est tracée dans `logs`, et une `commandes` est créée (coordonnées de livraison + lien vers la transaction et le marchand).

---

## 5. Flux de paiement détaillé

1. **Panier** — le client ajoute des cafés au panier sur la boutique, puis passe au paiement (paiement invité, sans compte).
2. **Saisie** — il renseigne ses coordonnées et sa carte (numéro, titulaire, MM/AA, CVV). La boutique valide le format côté client (Luhn, date, CVV).
3. **Encaissement** — `POST /api/checkout` : la boutique **recalcule le total côté serveur**, puis appelle PayPoc `POST /charge` (via le WAF, clé API) avec la carte.
4. **Validation** — PayPoc revalide la carte (Luhn, CVV, date). En cas d'échec → 422, aucun appel banque.
4b. **Validation bancaire (3DS)** — si la carte est **enrôlée** (connue d'un compte client, retrouvée via `crypt()` sur `numero_carte_hash`), le paiement n'est pas finalisé : la transaction passe en `PENDING`, la boutique affiche un écran d'attente et *poll* le statut, et le **porteur approuve/refuse** depuis son app banque (NovaPay : `GET/POST /api/authorizations`). À l'approbation → `COMPLETED` + crédit marchand + commande `PAID` ; au refus → `REJECTED`. Carte non enrôlée → autorisation instantanée classique (étape 5).

5. **Autorisation** — PayPoc appelle la banque (`POST /authorize`), puis enregistre une `transactions` (EXTERNAL-GATEWAY → marchand) :
   - **approuvé** → `COMPLETED` + `auth_code` + `bank_reference`, solde du marchand crédité ;
   - **refusé** → `REJECTED` + motif (carte de test), aucun crédit ;
   - **banque injoignable** → **rien n'est persisté** (transaction annulée), l'API renvoie 502.
   Chaque issue est journalisée (stdout JSON + table `logs`), **sans PAN ni CVV**.
6. **Confirmation** — la boutique affiche le résultat (référence commande + référence banque).

---

## 6. Observabilité

**Prometheus (métriques)** — `payment_payments_total{status}`, `payment_amount_euros_total`, `payment_bank_calls_total{outcome}`, `payment_card_validation_total{result}`, `bank_authorizations_total{decision,reason}`, métriques HTTP (débit, latence p95), nginx, PostgreSQL, conteneurs, sondes blackbox, boucle de résilience.

**Loki (logs)** — label `service` : `{service="api"}` événements métier JSON (`payment_approved`, `payment_declined`, `card_validation_failed`…), `{service="bank"}` décisions, `{service="waf"}` audit ModSecurity.

**Grafana** — dashboard *POC Resilience-Alpha — Vue d'ensemble* : disponibilité, paiements, décisions de la banque, taux d'approbation, trafic, latence, événements WAF, base, conteneurs, logs.

---

## 7. Sécurité

- **WAF ModSecurity/CRS** devant l'API PayPoc (SQLi, XSS, RCE, scanners…).
- **Aucune donnée de carte sensible** stockée ni journalisée : ni PAN complet, ni CVV, seulement `card_last4`, la marque et un `card_token` opaque (esprit PCI DSS).
- **Validation carte** (Luhn, CVV, date) côté passerelle avant tout appel banque.
- **SQL paramétré** partout, et rôle base `app_user` sans droit DDL.
- **Clé API** pour authentifier le marchand (serveur-à-serveur).
- **Total recalculé côté serveur** (jamais confiance au montant envoyé par le client).
- **Cloisonnement réseau** : base et banque jamais exposées.

---

## 8. Boucle de résilience autonome (détection → remédiation)

C'est le cœur du projet : attaque → détection → **réponse automatique sans intervention humaine** → service rétabli.

1. **ml-detector** interroge Prometheus (et Loki pour l'IP source) toutes les 5 s et construit un vecteur de features : débit req/s, taux d'erreurs 5xx, latence p95, taux de 4xx. Pendant ~2 min il apprend la « normale » et entraîne un **Isolation Forest**, puis score chaque mesure.
2. Après **3 anomalies consécutives**, il décide une action (flood → `block_ip` ou `restart_service` selon `FLOOD_ACTION` ; dégradation → `restart_service`) et appelle le moteur de remédiation (POST signé par token), puis respecte un temps de refroidissement.
3. **remediation** exécute le **playbook Ansible** correspondant :
   - `block_ip` : ajoute l'IP à la blocklist nginx (`map $http_x_forwarded_for`) du frontend et recharge nginx → les requêtes de cette IP tombent en 403 ;
   - `restart_service` : `docker restart` du conteneur ciblé (par label compose).
4. Le service revient à l'état nominal, prouvé par une **nouvelle transaction réussie**.

**Accès maîtrisé au moteur** (exigence du sujet) : `remediation` est sur un réseau interne dédié `remnet`, joignable uniquement par le détecteur, protégé par un token. C'est le **seul** composant avec accès au socket Docker. Garde-fous : IP jamais bloquées (`SAFE_IPS`), TTL de 5 min sur les blocages (déblocage automatique), anti-boucle sur les redémarrages.

## 9. Résilience et limites

- Si la banque est injoignable, le paiement reste **rejouable** (statut `created`) plutôt que perdu.
- Verrouillage du paiement à la confirmation → pas de double débit concurrent.
- Soldes de la banque **en mémoire** : réinitialisés au redémarrage du conteneur (acceptable pour un POC ; à remplacer par une base si persistance voulue).
- `cadvisor` fonctionne mal sous Docker Desktop (lancer avec `--scale cadvisor=0`).

Suite prévue (cyber-résilience) : générateur de trafic légitime (baseline), détecteur d'anomalies (Isolation Forest) lisant Prometheus/Loki, moteur de remédiation (Ansible : block ip, restart, scale), sauvegarde/restauration PostgreSQL.

---

## 10. Démarrage rapide

```bash
cp .env.example .env            # puis remplacer les "change-me"
docker compose up -d --build --scale cadvisor=0
./scripts/smoke-test.sh
```

| Interface | URL | Identifiants |
|---|---|---|
| Boutique Brûlerie du Comptoir | http://localhost:8082 | — (paiement invité) |
| Façade PayPoc (API derrière le WAF) | http://localhost | — |
| Grafana | http://localhost:3000 | `admin` / `GRAFANA_ADMIN_PASSWORD` |
| Prometheus | http://localhost:9090 | — |
