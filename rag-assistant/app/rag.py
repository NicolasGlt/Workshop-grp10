"""Cœur du RAG : index vectoriel en mémoire (sauvé en JSON) et réponse en français.

Aucun outil, aucun accès à Docker, à la base ni aux journaux (mesure M11 de l'EBIOS) :
l'assistant ne fait que chercher dans le corpus et rédiger une réponse avec ses sources.
"""
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_ollama import ChatOllama, OllamaEmbeddings

from . import config, corpus

_SYSTEM = (
    "Tu es l'assistant local des opérateurs du projet RESILIENCE-ALPHA (groupe 10). "
    "Tu réponds en français, de façon concise, en t'appuyant UNIQUEMENT sur les extraits "
    "de documentation fournis ci-dessous. "
    "Si les extraits ne contiennent pas la réponse, réponds exactement « Je ne sais pas » "
    "sans rien inventer. "
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
    return ChatOllama(model=config.RAG_MODEL, base_url=config.OLLAMA_URL, temperature=0)


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


def answer(question, store=None):
    """Répond à `question` à partir du corpus. Renvoie {answer, sources}."""
    store = store or load_store()
    docs = store.similarity_search(question, k=config.TOP_K)
    if not docs:
        return {"answer": "Je ne sais pas", "sources": []}
    prompt = (
        f"{_SYSTEM}\n\n"
        f"Extraits de documentation :\n\n{_format_context(docs)}\n\n"
        f"Question de l'opérateur : {question}"
    )
    reponse = _chat().invoke(prompt).content.strip()
    return {"answer": reponse, "sources": _sources(docs)}
