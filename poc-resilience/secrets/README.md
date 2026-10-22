# Secrets du POC : SOPS + age

Exigence §3.4 du sujet (« gestion des secrets avec HashiCorp Vault ou SOPS »). L'équipe a retenu **SOPS + age** : pas de serveur à faire tourner, le fichier chiffré vit dans Git, et chaque valeur est chiffrée séparément (les noms de variables restent lisibles dans une revue de code, les valeurs non).

> Installation neuve ou examen du projet : ce mécanisme n'est pas nécessaire. `just env` génère des secrets locaux ([GUIDE-WINDOWS.md](../../GUIDE-WINDOWS.md#4-générer-la-configuration)). Les fichiers chiffrés ne servent qu'aux membres de l'équipe.

Deux services ont des secrets chiffrés (`poc-resilience` et `auth-faciale`), avec la convention `<service>/.env` ⟷ `<service>/secrets/<service>.enc.env`. La liste des services est dans le `justfile` (`secrets_services`).

| Fichier | Versionné | Rôle |
|---|---|---|
| `poc-resilience/.env`, `auth-faciale/.env` | non (`.gitignore`) | secrets en clair, lus par Docker Compose |
| `poc-resilience/secrets/poc-resilience.enc.env` | oui | le `.env` du POC, chiffré par SOPS (format dotenv) |
| `auth-faciale/secrets/auth-faciale.enc.env` | oui | le `.env` du back-office auth-faciale, chiffré de même |
| `.sops.yaml` (racine) | oui | règles de création : quels fichiers, pour quelles clés **publiques** |
| clé privée age | **jamais** | `~/.config/sops/age/keys.txt` (Linux), `%AppData%\sops\age\keys.txt` (Windows) |

## Principe : une clé par personne, aucune clé privée qui voyage

SOPS chiffre une clé de données pour **chaque destinataire** listé dans `.sops.yaml`. Chaque membre a donc sa propre paire age, et personne n'envoie jamais sa clé privée : seule la clé publique (`age1...`) circule, et elle n'est pas un secret. Le PC Hôte de la démo a sa propre paire, comme un membre.

Ce choix évite le partage d'une clé privée commune (par messagerie, clé USB...) : le départ d'un membre se traite en retirant sa clé publique puis en lançant `just secrets-updatekeys`, puis en changeant les mots de passe qu'il a pu lire.

## Mise en place

Outils : `sops` ≥ 3.9 (sous-commandes `encrypt`/`decrypt`, option `--filename-override`) et `age`, depuis les publications officielles des projets (`getsops/sops`, `FiloSottile/age` sur GitHub) ; sous Debian, `age` est aussi en paquet.

1. **Chaque membre** crée sa paire, hors dépôt, puis copie la clé publique affichée :
   ```bash
   just secrets-keygen
   ```
2. Il **envoie sa clé publique** par une PR qui l'ajoute dans `.sops.yaml` (liste séparée par des virgules sous `age:`). La revue de la PR vaut contrôle d'accès : on voit qui peut déchiffrer.
3. **Premier chiffrement** (une fois, par un membre qui a les `.env` complets), après avoir remplacé `age1-CLE-PUBLIQUE-A-REMPLACER` :
   ```bash
   just secrets-encrypt
   ```
   chiffre le `.env` de chaque service ; commiter les `*.enc.env` produits.
   Sous Windows, si `secrets-encrypt` répond `invalid dotenv input line`, un `.env` est en CRLF : le parseur dotenv de SOPS exige des fins de ligne LF. Reconvertir le fichier en LF (bouton « CRLF → LF » de l'éditeur, ou `dos2unix <service>/.env`) puis relancer. Les modèles `*/.env.example` sont déjà en LF (`.gitattributes`), donc un `.env` copié depuis l'un d'eux n'a pas le souci.
4. **Après l'ajout d'une clé publique**, un membre qui peut déjà déchiffrer lance `just secrets-updatekeys` et commite le fichier : le nouveau venu peut alors déchiffrer.

## Déchiffrer sur son poste

Une fois sa clé publique présente dans `.sops.yaml` et les fichiers rechiffrés pour elle (étape 4 ci-dessus), le membre régénère les `.env` en clair depuis le dépôt :

```bash
just secrets-decrypt   # régénère le .env de chaque service à partir de son fichier chiffré
```

SOPS lit la clé privée dans `%AppData%\sops\age\keys.txt` (Windows) ou `~/.config/sops/age/keys.txt` (Linux) ; aucun argument de clé à passer. Si le poste n'a pas encore de clé, voir l'étape 1. Chaque `.env` régénéré contient toutes les variables et commentaires ; seules les lignes vides décoratives sautent (SOPS ne les restitue pas en format dotenv), ce qui n'a aucun effet sur Docker Compose.

## Usage courant

| Besoin | Commande |
|---|---|
| Obtenir les `.env` sur un poste neuf (ou le PC Hôte) | `just secrets-decrypt` (tous les services) |
| Changer un secret | `just secrets-edit <service>` (déchiffré le temps de l'éditeur ; défaut `poc-resilience`), ou modifier le `.env` puis `just secrets-encrypt` |
| Ajouter ou retirer un membre | modifier `.sops.yaml`, puis `just secrets-updatekeys` (tous les services) |
| Chiffrer un nouveau service | ajouter son nom à `secrets_services` (`justfile`) et une règle dans `.sops.yaml`, puis `just secrets-encrypt` |

## Limites assumées

- Les conteneurs lisent toujours un `.env` en clair sur le disque de l'hôte : SOPS protège le dépôt et la distribution, pas le poste. C'est la limite connue face à un Vault qui délivrerait les secrets à l'exécution.
- Un secret qui a été lisible par un membre sorti reste compromis : retirer sa clé ne suffit pas, il faut changer la valeur.
- Les fichiers chiffrés se gardent en fins de ligne LF (le `secrets/.gitattributes` de chaque service), sinon le MAC de SOPS ne correspond plus.
