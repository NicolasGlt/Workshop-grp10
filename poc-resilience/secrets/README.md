# Secrets du POC : SOPS + age

Exigence §3.4 du sujet (« gestion des secrets avec HashiCorp Vault ou SOPS »). L'équipe a retenu **SOPS + age** : pas de serveur à faire tourner, le fichier chiffré vit dans Git, et chaque valeur est chiffrée séparément (les noms de variables restent lisibles dans une revue de code, les valeurs non).

| Fichier | Versionné | Rôle |
|---|---|---|
| `poc-resilience/.env` | non (`.gitignore`) | secrets en clair, lus par Docker Compose |
| `poc-resilience/secrets/poc-resilience.enc.env` | oui | le même `.env`, chiffré par SOPS (format dotenv) |
| `.sops.yaml` (racine) | oui | règle de création : quels fichiers, pour quelles clés **publiques** |
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
3. **Premier chiffrement** (une fois, par un membre qui a un `.env` complet), après avoir remplacé `age1-CLE-PUBLIQUE-A-REMPLACER` :
   ```bash
   just secrets-encrypt
   ```
   puis commit de `poc-resilience/secrets/poc-resilience.enc.env`.
4. **Après l'ajout d'une clé publique**, un membre qui peut déjà déchiffrer lance `just secrets-updatekeys` et commite le fichier : le nouveau venu peut alors déchiffrer.

## Usage courant

| Besoin | Commande |
|---|---|
| Obtenir le `.env` sur un poste neuf (ou le PC Hôte) | `just secrets-decrypt` |
| Changer un secret | `just secrets-edit` (déchiffré le temps de l'éditeur), ou modifier `.env` puis `just secrets-encrypt` |
| Ajouter ou retirer un membre | modifier `.sops.yaml`, puis `just secrets-updatekeys` |

## Limites assumées

- Les conteneurs lisent toujours un `.env` en clair sur le disque de l'hôte : SOPS protège le dépôt et la distribution, pas le poste. C'est la limite connue face à un Vault qui délivrerait les secrets à l'exécution.
- Un secret qui a été lisible par un membre sorti reste compromis : retirer sa clé ne suffit pas, il faut changer la valeur.
- Le fichier chiffré se garde en fins de ligne LF (`secrets/.gitattributes`), sinon le MAC de SOPS ne correspond plus.
