"""Cœur du RAG : index vectoriel en mémoire (sauvé en JSON) et réponse en français.

Aucun outil, aucun accès à Docker, à la base ni aux journaux (mesure M11 de l'EBIOS) :
l'assistant ne fait que chercher dans le corpus et rédiger une réponse avec ses sources.
"""
import json
from datetime import datetime, timezone

from langchain_core.vectorstores import InMemoryVectorStore
from langchain_ollama import ChatOllama, OllamaEmbeddings

from . import config, corpus

_SYSTEM = (
    "Tu es l'assistant local des opérateurs du projet RESILIENCE-ALPHA (groupe 10). "
    "Tu réponds en français, de façon concise et actionnable, en t'appuyant sur les extraits "
    "de documentation fournis ci-dessous, y compris les tableaux : rapproche la question de "
    "l'opérateur du symptôme ou de la procédure documentés même si la formulation diffère "
    "(ex. « ne détecte pas le flood » correspond à « pas de remédiation pendant le flood »). "
    "Si un extrait décrit la situation, donne la marche à suivre qu'il indique. "
    "Si VRAIMENT aucun extrait n'aborde le sujet, réponds EXACTEMENT par le seul mot "
    "« INCONNU » (en majuscules, sans aucun autre texte) ; n'invente jamais une "
    "information absente des extraits. "
    "Tu n'as aucun outil et aucun accès au système : tu n'exécutes rien toi-même et tu ne "
    "fais que rapporter ce que dit la documentation (tu peux citer une commande documentée, "
    "mais c'est l'opérateur qui la lance). "
    "Ne liste pas les sources toi-même : l'interface les affiche automatiquement sous ta réponse."
)


def _embeddings():
    return OllamaEmbeddings(model=config.EMBED_MODEL, base_url=config.OLLAMA_URL)


def _chat():
    if not config.RAG_MODEL:
        raise RuntimeError(
            "RAG_MODEL n'est pas défini : copier dans rag-assistant/.env le nom exact "
            "donné par `ollama list` sur le PC Hôte."
        )
    # reasoning=False : le qwen3.5 passe en mode « raisonnement » sur un prompt complexe et
    # ne renvoie alors aucune réponse finale (content vide). On le désactive pour cet usage.
    return ChatOllama(model=config.RAG_MODEL, base_url=config.OLLAMA_URL,
                      temperature=0, reasoning=False)


# --- index ----------------------------------------------------------------------------

def build_index():
    """(Re)construit l'index depuis le corpus et le sauve en JSON. Renvoie le nombre de morceaux."""
    chunks = corpus.load_chunks()
    if not chunks:
        raise RuntimeError("corpus vide : aucun fichier Markdown trouvé")
    store = InMemoryVectorStore(_embeddings())
    store.add_documents(chunks)
    config.INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    store.dump(config.INDEX_PATH)
    return len(chunks)


def load_store():
    """Recharge l'index JSON. Lève une erreur claire s'il n'a pas encore été construit."""
    if not config.INDEX_PATH.exists():
        raise FileNotFoundError(
            f"index absent ({config.INDEX_PATH}) : lancer `just assistant-index` d'abord"
        )
    return InMemoryVectorStore.load(str(config.INDEX_PATH), _embeddings())


# --- réponse --------------------------------------------------------------------------

def _format_context(docs):
    blocs = []
    for i, doc in enumerate(docs, 1):
        titre = doc.metadata.get("title") or "(sans titre)"
        source = doc.metadata.get("source", "?")
        blocs.append(f"[Extrait {i}] Fichier : {source} — Titre : {titre}\n{doc.page_content}")
    return "\n\n".join(blocs)


def _sources(docs):
    """Sources dédupliquées (fichier + titre), dans l'ordre d'apparition."""
    vues, out = set(), []
    for doc in docs:
        cle = (doc.metadata.get("source"), doc.metadata.get("title"))
        if cle not in vues:
            vues.add(cle)
            out.append({"source": cle[0], "title": cle[1]})
    return out


_FALLBACK_SYSTEM = (
    "Tu es l'assistant local des opérateurs du projet RESILIENCE-ALPHA (groupe 10). "
    "AUCUN extrait de la documentation de l'équipe ne répond à la question. "
    "Tu peux proposer une piste générale pour aider l'opérateur à avancer, mais elle "
    "n'est PAS validée par l'équipe : reste prudent, n'invente pas de commande ni de "
    "chemin propres à ce projet, et indique quoi vérifier. Réponds en français, concis. "
    "Tu n'as aucun outil et aucun accès au système."
)

_LACUNES = config.INDEX_PATH.parent / "lacunes.jsonl"


def _journalise_lacune(question):
    """Trace une question sans réponse dans le corpus, pour enrichissement humain ultérieur
    (choix d'équipe : pas d'auto-insertion de contenu non vérifié dans la base de confiance)."""
    try:
        config.INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        ligne = json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "question": question},
                           ensure_ascii=False)
        with _LACUNES.open("a", encoding="utf-8") as f:
            f.write(ligne + "\n")
    except Exception:
        pass


def answer(question, store=None):
    """Répond à `question`. D'abord depuis le corpus ; si rien de pertinent, réponse de
    secours étiquetée « hors documentation » et la lacune est journalisée pour qu'un humain
    enrichisse le corpus après validation. Renvoie {answer, sources, grounded}."""
    store = store or load_store()
    docs = store.similarity_search(question, k=config.TOP_K)
    if docs:
        prompt = (
            f"{_SYSTEM}\n\n"
            f"Extraits de documentation :\n\n{_format_context(docs)}\n\n"
            f"Question de l'opérateur : {question}"
        )
        reponse = _chat().invoke(prompt).content.strip()
        inconnu = (not reponse) or reponse.strip('«».," ').upper().startswith("INCONNU")
        if not inconnu:
            return {"answer": reponse, "sources": _sources(docs), "grounded": True}
    # Le corpus ne répond pas : piste de secours non validée + trace de la lacune.
    _journalise_lacune(question)
    reponse = _chat().invoke(
        f"{_FALLBACK_SYSTEM}\n\nQuestion de l'opérateur : {question}"
    ).content.strip()
    etiquette = "[Hors documentation de l'équipe — à vérifier]\n\n"
    return {"answer": etiquette + (reponse or "Je ne sais pas"), "sources": [], "grounded": False}
