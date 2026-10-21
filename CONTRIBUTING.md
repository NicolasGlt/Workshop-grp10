# Contribuer au dépôt

## Branches et pull requests

On ne pousse pas directement sur `main`. Chaque modification part d'une branche à jour et passe par une pull request relue par un autre membre.

```bash
git switch main && git pull
git switch -c feature/assistant-rag-ollama
```

Nom de branche : `type/description` en minuscules avec des tirets ([Conventional Branch](https://conventionalbranch.org/)). Types : `feature/`, `fix/`, `chore/` (config, doc, ménage).

## Commits

Format [Conventional Commits](https://www.conventionalcommits.org/fr/v1.0.0/) : `type(dossier): description`, par exemple `fix(poc): rétablit le healthcheck de bank`. Types : `feat`, `fix`, `docs`, `chore`.

Pas de secret dans les commits : les vraies valeurs vont dans `.env`, qui est ignoré par Git.

## Gel du code

Jeudi 22/10 à 17h. Après, seules les corrections validées par l'équipe entrent dans `main`.
