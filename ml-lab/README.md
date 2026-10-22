# Resilience ML Local Lab

POC local et autonome de détection d'anomalies pour une plateforme de paiement.

## Ce que fait le projet

- génère des fenêtres de logs synthétiques et des états de santé ;
- entraîne deux Isolation Forest : comportement global et nouveauté textuelle ;
- calibre les seuils sur un jeu normal séparé ;
- teste des incidents connus et une famille d'erreurs inconnues pendant l'entraînement ;
- localise le composant probablement défaillant ;
- propose uniquement une remédiation issue d'une liste blanche ;
- expose ensuite le moteur avec FastAPI.

Aucune attaque réseau réelle n'est lancée. Tout est simulé en mémoire ou dans des fichiers JSONL/CSV.

## Prérequis

Python 3.11+ recommandé. Sous Windows, depuis `ml-lab\` :

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest
.venv\Scripts\python scripts\run_all.py
```

Sur macOS ou Linux :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Lancement complet

```bash
python scripts/run_all.py
```

Cette commande génère les données, entraîne les modèles, exécute l'évaluation et écrit :

- `artifacts/model.joblib`
- `artifacts/calibration.json`
- `artifacts/evaluation.csv`
- `artifacts/report.json`

## Démonstration interactive

```bash
python -m app.cli list-scenarios
python -m app.cli simulate --scenario api_down --count 5
python -m app.cli simulate --scenario unknown_runtime --count 5
python -m app.cli replay-all
```

## API locale

```bash
uvicorn app.api:app --reload --port 8090
```

Documentation interactive : http://127.0.0.1:8090/docs

Exemples :

```bash
curl http://127.0.0.1:8090/health
curl -X POST http://127.0.0.1:8090/simulate/api_down
curl -X POST http://127.0.0.1:8090/simulate/unknown_runtime
```

## Scénarios synthétiques

- `normal`
- `api_down`
- `db_down`
- `frontend_down`
- `bank_timeout`
- `traffic_flood`
- `auth_abuse`
- `waf_attack`
- `memory_pressure`
- `latency_spike`
- `unknown_runtime` : messages jamais vus à l'entraînement
- `silent_failure` : service muet et health check dégradé

## Philosophie de sécurité

Le ML détecte l'inconnu, mais ne fabrique jamais une commande. Le moteur retourne une action abstraite autorisée telle que `restart_payment_api`. Dans cette version locale, l'exécuteur ne fait qu'écrire ce qu'il aurait fait. La future intégration Ansible traduira cette action en playbook connu.

## Réglages principaux

Dans `app/config.py` : tailles des datasets, arbres, seuils de calibration et graine aléatoire. Pour un Mac avec 24 Go de RAM, les réglages par défaut sont volontiers plus lourds qu'un simple exemple, mais restent raisonnables. Augmenter `TRAIN_NORMAL_WINDOWS` à 20000 et `N_ESTIMATORS` à 800 pour une expérimentation plus longue.

## Limite importante

Une anomalie signifie « différent du normal appris », pas « attaque prouvée ». Les colonnes `scenario_truth` ne sont utilisées que pour l'évaluation, jamais pour entraîner le modèle.
