# Assistant RAG des opérateurs

Assistant local qui répond aux questions des opérateurs face à l'incident, **à partir de la
documentation du projet** (procédures, architecture, fiche du jour J). Construit avec
**Ollama** (modèle local) et **LangChain** en **RAG** sur les fichiers Markdown de l'équipe
(consigne §3.3 du sujet).

## Rôle et limites

- Il **informe** : il cherche les passages pertinents du corpus et rédige une réponse en
  français **avec ses sources** (fichier et titre). S'il ne trouve pas, il répond « Je ne sais pas ».
- Il **n'agit pas sur le SI** : aucun outil, aucun accès à Docker, à la base ni aux journaux
  (mesure **M11** de l'EBIOS). Ce n'est **ni** l'automate de remédiation Ansible, **ni** un compte
  à privilèges : il ne fait que lire des fichiers texte et parler à Ollama en local.
- Tout tourne sur **127.0.0.1** : rien n'est exposé sur le réseau de la démo.

## Modèle : écart assumé 9B vs 8B

Le sujet suggère un modèle ≤ 8B. L'équipe garde le **Qwen 9B déjà installé sur le PC Hôte**,
par choix : il **tient sur la RTX 4070 (12 Go)** et **répond mieux**. L'écart est assumé et le
modèle reste **configurable** par `RAG_MODEL` dans `.env` : copier le nom exact donné par
`ollama list`. Pour un poste plus modeste, mettre un modèle plus petit (`qwen2.5:3b`,
`qwen3:1.7b`, etc.) ; le smoke test de développement a été passé avec `qwen2.5:3b`.

## Pile technique

Python 3.12 pur, **aucune dépendance native fragile** (pas de Chroma ni de FAISS) : l'index
vit en mémoire (`InMemoryVectorStore` de `langchain-core`) et se **sauve en JSON**. Paquets
épinglés dans [`requirements.txt`](requirements.txt).

## Installation Windows (PC Hôte) pas à pas

Depuis la **racine du dépôt**, avec Ollama déjà installé et lancé sur le PC Hôte :

```powershell
# 1. Environnement Python (crée .venv et copie .env.example -> .env)
just assistant-install

# 2. Renseigner le modèle : ouvrir rag-assistant\.env et coller dans RAG_MODEL
#    le nom EXACT affiché par :
ollama list
#    (par ex. le Qwen 9B présent). Récupérer aussi le modèle d'embeddings si besoin :
ollama pull nomic-embed-text

# 3. Construire l'index depuis le corpus de l'équipe
just assistant-index

# 4. Vérifier que tout est prêt (Ollama, modèles, index, question test)
just assistant-check

# 5. Lancer l'assistant : http://127.0.0.1:8001
just assistant
```

Sous Linux, les mêmes recettes `just` fonctionnent (variantes `[unix]`).

## Corpus

Documents de l'équipe (en lecture seule) listés dans [`app/config.py`](app/config.py) :
`README.md`, `docs/demo-jour-j.md`, `poc-resilience/README.md` et ses `docs/*.md`,
`poc-resilience/secrets/README.md`, `auth-faciale/docs/*.md`, `ml-lab/README.md`.
Pour en ajouter (PCA/PRA, FAQ…), déposer des `.md` ou `.txt` dans
[`corpus/`](corpus/) puis relancer `just assistant-index`.

Découpage : d'abord par **titres Markdown** (H1/H2/H3), puis par **taille**.

## API

- `POST /api/ask` — corps `{"question": "..."}`, réponse `{"answer": "...", "sources": [...]}`.
- `GET /api/health` — état de la configuration (index présent, URL Ollama, modèles).

## Configuration (`.env`)

| Variable | Défaut | Rôle |
|---|---|---|
| `OLLAMA_URL` | `http://127.0.0.1:11434` | serveur Ollama du PC Hôte |
| `RAG_MODEL` | *(vide)* | **à renseigner** : nom exact de `ollama list` |
| `EMBED_MODEL` | `nomic-embed-text` | modèle d'embeddings |
| `PORT` | `8001` | 8000 est pris par le back-office |

`.env` n'est jamais versionné ; seul `.env.example` l'est. Aucun secret dans ce module.
