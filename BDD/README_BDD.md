# BDD Payment

Cette stack lance :

```text
PostgreSQL 16
├── Base paymentdb
├── Tables et fonctions SQL créées par init.sql
└── Données de test créées par seed.sql

pgAdmin
└── Interface Web de gestion PostgreSQL

FastAPI
├── Création de comptes
├── Vérification des mots de passe
├── Création de comptes bancaires
└── Ajout sécurisé des cartes de test
```

## Configuration `.env`

Créer `.env` à partir du modèle si le fichier n'existe pas :

```bash
cp .env.example .env
```

Configurer ensuite les variables :

```env
POSTGRES_DB=paymentdb
POSTGRES_USER=payment_admin
POSTGRES_PASSWORD=change-me
POSTGRES_PORT=5432

PGADMIN_EMAIL=admin@example.com
PGADMIN_PASSWORD=change-me
PGADMIN_PORT=8080

API_PORT=8000
```

Le fichier `.env` contient les mots de passe locaux et ne doit pas être envoyé sur GitHub.

## Lancement

Depuis la racine du dépôt, dans le dossier contenant `docker-compose.yml` :

```bash
docker compose -f ./docker-compose.yml --env-file ./.env up -d --build
```

Pour les lancements suivants :

```bash
docker compose -f ./docker-compose.yml --env-file ./.env up -d
```

Vérifier les services :

```bash
docker compose -f ./docker-compose.yml --env-file ./.env ps
```

Afficher les logs :

```bash
docker compose -f ./docker-compose.yml --env-file ./.env logs -f
```

Arrêter sans supprimer les données :

```bash
docker compose -f ./docker-compose.yml --env-file ./.env down
```

Réinitialiser entièrement la BDD :

```bash
docker compose -f ./docker-compose.yml --env-file ./.env down -v
docker compose -f ./docker-compose.yml --env-file ./.env up -d --build
```

La réinitialisation supprime les données locales et rejoue `init.sql` et `seed.sql`.

## Accès

### pgAdmin

```text
http://127.0.0.1:8080
```

Connexion avec `PGADMIN_EMAIL` et `PGADMIN_PASSWORD` du `.env`.

Le serveur `PaymentDB` est préconfiguré. Si pgAdmin demande le mot de passe PostgreSQL, utiliser `POSTGRES_PASSWORD`.

### API FastAPI

```text
Documentation : http://127.0.0.1:8000/docs
État API      : http://127.0.0.1:8000/health
```

### PostgreSQL

```text
Hôte          : 127.0.0.1
Port          : 5432
Base          : paymentdb
Utilisateur   : payment_admin
Mot de passe  : POSTGRES_PASSWORD du .env
```

## Fonctionnement du hash

Lors de la création d'un compte par `POST /accounts`, l'API appelle la fonction SQL `creer_compte()`.

Cette fonction utilise bcrypt et enregistre uniquement le résultat dans `password_hash` :

```text
Mot de passe reçu
        ↓
Fonction hash_password()
        ↓
Hash bcrypt $2a$12$...
        ↓
Colonne comptes.password_hash
```

Le mot de passe en clair n'est pas conservé.

La route `POST /auth/verify-password` compare le mot de passe fourni avec le hash enregistré et renvoie :

```json
{
  "valid": true
}
```

ou :

```json
{
  "valid": false
}
```

Pour les cartes de test :

- `card_token` sert de référence pour l'API bancaire simulée ;
- `card_last4` conserve seulement les quatre derniers chiffres pour l'affichage ;
- les champs prévus comme sensibles sont hashés ;
- aucun CVV n'est accepté ni enregistré.

## Routes disponibles

```text
GET  /health
POST /accounts
POST /auth/verify-password
POST /bank-accounts
POST /cards
```
