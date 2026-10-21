# Resilience-Alpha — Documentation technique

Plateforme de paiement conteneurisée (Docker Compose) : une boutique encaisse via une passerelle, derrière un WAF, avec supervision et **remédiation autonome**. Aucune donnée bancaire réelle.

## Architecture (services)

| Service | Rôle | Techno | Exposé |
|---|---|---|---|
| `waf` | Pare-feu applicatif (point d'entrée API) | nginx + ModSecurity / OWASP CRS | :80 |
| `frontend` | Reverse-proxy `/api` + blocklist dynamique | nginx | via WAF |
| `merchant` | Boutique « Brûlerie du Comptoir » (catalogue, panier, checkout, **comptes clients**) | FastAPI + SPA | :8082 |
| `api` (PayPoc) | Passerelle de paiement | FastAPI | via WAF |
| `bank` | Banque fictive (décision par cartes de test) | FastAPI | interne |
| `accounts-api` | API comptes/cartes (partie BDD du groupe) | FastAPI | :8081 |
| `clientapp` (NovaPay) | Espace client néobanque (lecture seule) | FastAPI + SPA | :8083 |
| `db` | Base de données | PostgreSQL 16 | interne |
| `pgadmin` | Console d'admin BDD | pgAdmin 4 | :5050 |
| `ml-detector` + `remediation` | Détection d'anomalies → remédiation Ansible | scikit-learn, Ansible | interne |
| `prometheus` + exporters, `loki` + `alloy`, `grafana` | Métriques, logs, dashboards | — | :9090 / :3000 |

**Réseaux Docker** : `edge` (exposé) ; `app`, `data`, `remnet` **internes** (la base et la banque ne sont jamais publiées) ; `monitoring` pour la collecte. Un conteneur présent uniquement sur un réseau `internal` ne peut pas publier de port.

## Flux d'un paiement

1. Le client remplit panier + livraison + carte sur la **boutique**.
2. `merchant` recalcule le total côté serveur et appelle **PayPoc** `POST /charge` (via le WAF, authentifié par clé API marchand). S'il est connecté, il transmet son `id_compte`.
3. **PayPoc** valide la carte (Luhn, CVV, date) *avant* tout appel banque ; en cas d'échec → 422.
4. PayPoc demande l'autorisation à la **banque** (`/authorize`, cartes de test déterministes).
5. PayPoc écrit, dans une seule transaction SQL : une `transactions` (`COMPLETED`/`REJECTED`), le crédit du solde marchand si accepté, une `commandes` (livraison + liens), et une entrée `logs`. Banque injoignable → 502, rien n'est persisté.

## API (principaux endpoints)

- **PayPoc** : `POST /api/charge` (clé API), `GET /api/payments/{id}`, `GET /api/ping`.
- **Boutique** : `GET /api/products`, `POST /api/checkout`, `POST /api/register`, `POST /api/login`, `GET /api/account` (JWT).
- **NovaPay** : `POST /api/login`, `GET /api/accounts|cards|transactions` (JWT).
- **accounts-api** : `POST /accounts|bank-accounts|cards`, `POST /auth/verify-password`.

## Base de données

Modèle bancaire du groupe (socle) : `utilisateurs`, `comptes` (email + `password_hash` bcrypt), `comptes_bancaires` (solde), `cartes` (token + `card_last4`), `transactions`, `logs` — + fonctions SQL `creer_compte`, `ajouter_compte_bancaire`, `ajouter_carte`, `verify_password`. Ajouts passerelle (sans modifier le modèle) : `merchants` (marchand → compte d'encaissement) et `commandes` (achat boutique, reliée au marchand + à la transaction ; `id_compte` si client connecté, sinon NULL ; jamais de lien vers un compte bancaire). Rôle applicatif `app_user` à **privilèges minimaux** (aucun DDL). Init exécutée dans l'ordre : `01-core` → `02-gateway` → `03-seed` → `04-roles`.

## Sécurité & résilience

- **Esprit PCI-DSS** : le numéro de carte et le CVV ne sont **jamais stockés ni journalisés** ; seuls `card_last4`, un token opaque et la référence banque sont conservés. Seule la banque voit le PAN complet (en mémoire). SQL paramétré partout.
- **Résilience autonome** : un *Isolation Forest* apprend la normale ; sur anomalie (ex. flood type DoS) il déclenche automatiquement des playbooks Ansible (blocage d'IP, redémarrage de service) — sans intervention humaine.

## Démarrage

```bash
cp .env.example .env    # renseigner les secrets
docker compose up -d --build
```
Boutique :8082 · NovaPay :8083 · API comptes :8081/docs · pgAdmin :5050 · Grafana :3000.
