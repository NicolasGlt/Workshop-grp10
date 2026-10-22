"""Lecture du corpus (Markdown de l'équipe) et découpage par titres puis par taille.

Le corpus est en lecture seule : on ne lit que des fichiers texte du dépôt et le
dossier rag-assistant/corpus/. Aucun accès à Docker, à la base ni aux journaux.
"""
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from . import config

_HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]


def _source_files():
    """Chemins absolus des fichiers du corpus, sans doublon, dans l'ordre de config."""
    seen = []
    for motif in config.CORPUS_SOURCES:
        for path in sorted(config.REPO.glob(motif)):
            if path.is_file() and path not in seen:
                seen.append(path)
    # Textes libres déposés par l'équipe (PCA/PRA, etc.)
    if config.CORPUS_DIR.exists():
        for path in sorted(config.CORPUS_DIR.rglob("*")):
            if path.is_file() and path.suffix.lower() in (".md", ".txt") and path not in seen:
                seen.append(path)
    return seen


def _relative(path):
    """Chemin lisible, relatif à la racine du dépôt, en séparateurs POSIX."""
    try:
        return path.relative_to(config.REPO).as_posix()
    except ValueError:
        return path.name


def _title(meta):
    """Fil d'Ariane des titres Markdown du morceau, ex. « Plan B > Symptôme »."""
    parts = [meta[k] for k in ("h1", "h2", "h3") if meta.get(k)]
    return " > ".join(parts)


def load_chunks():
    """Renvoie la liste des morceaux (Document) prêts à être indexés.

    Chaque morceau porte dans ses métadonnées `source` (fichier) et `title` (titre).
    """
    header_splitter = MarkdownHeaderTextSplitter(_HEADERS, strip_headers=False)
    size_splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP
    )
    chunks = []
    for path in _source_files():
        source = _relative(path)
        text = path.read_text(encoding="utf-8")
        for section in header_splitter.split_text(text):
            title = _title(section.metadata)
            for piece in size_splitter.split_text(section.page_content):
                content = piece.strip()
                if content:
                    chunks.append(Document(
                        page_content=content,
                        metadata={"source": source, "title": title},
                    ))
    return chunks


def list_sources():
    """Liste lisible des fichiers du corpus (pour assistant-check et le README)."""
    return [_relative(p) for p in _source_files()]
