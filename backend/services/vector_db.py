"""Semantic search over the legacy 0.x prompt table, backed by ChromaDB.

ChromaDB is optional
--------------------
This module used to import ``chromadb`` at module scope. The legacy routers import this
module, and ``backend.main`` imports those routers — so the **whole application**,
including the modern ``/v1`` API which does not use vectors at all, refused to start
unless a large ML dependency was installed.

That coupling is now removed. ChromaDB is loaded lazily on first use; if it is absent,
semantic search degrades to a clearly-reported no-op and every other endpoint works.

The practical effect: ``/v1`` — the surface third parties build against — runs with a
small dependency set, which is also what makes the end-to-end suite runnable in
environments that have no interest in vector search.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from uuid import UUID

logger = logging.getLogger("assay.vector_db")

_project_root = Path(__file__).resolve().parent.parent.parent
CHROMA_DATA_PATH = os.getenv("CHROMA_DATA_PATH", str(_project_root / "chroma_data"))

#: Resolved on first use: the collection, or None when ChromaDB is unavailable.
_collection = None
_unavailable_reason: str | None = None


def _get_collection():
    """Return the Chroma collection, or ``None`` if ChromaDB cannot be used.

    Failure is cached, so a missing dependency costs one import attempt rather than one
    per request.
    """
    global _collection, _unavailable_reason
    if _collection is not None or _unavailable_reason is not None:
        return _collection

    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except Exception as exc:
        _unavailable_reason = f"chromadb not installed ({exc})"
        logger.info(
            "semantic search disabled: %s. Everything else, including /v1, is unaffected.",
            _unavailable_reason,
        )
        return None

    try:
        client = chromadb.PersistentClient(path=CHROMA_DATA_PATH)
        _collection = client.get_or_create_collection(
            name="prompts",
            embedding_function=embedding_functions.DefaultEmbeddingFunction(),
        )
    except BaseException as exc:
        # Some native extensions (notably pyo3) surface Rust panics as a
        # ``BaseException`` subclass rather than ``Exception``.  Semantic search is
        # optional and must not take down prompt writes, but genuine process-control
        # signals must retain their normal behaviour.
        if isinstance(exc, (KeyboardInterrupt, SystemExit, GeneratorExit)):
            raise
        _unavailable_reason = f"chromadb failed to initialise ({exc})"
        logger.warning("semantic search disabled: %s", _unavailable_reason)
        return None
    return _collection


def is_available() -> bool:
    """Whether semantic search can actually run.

    Endpoints should report this rather than silently returning nothing — an empty
    result set that means "not installed" is indistinguishable from "no matches".
    """
    return _get_collection() is not None


def unavailable_reason() -> str | None:
    _get_collection()
    return _unavailable_reason


def add_prompt_embedding(prompt_id: UUID, text: str, metadata: dict) -> bool:
    """Index a prompt. Returns False when semantic search is unavailable.

    Indexing must never break a write: creating a prompt is the user's intent; adding it
    to a vector index is a side effect.
    """
    collection = _get_collection()
    if collection is None:
        return False
    try:
        collection.upsert(ids=[str(prompt_id)], documents=[text], metadatas=[metadata])
        return True
    except Exception as exc:
        logger.warning("could not index prompt %s: %s", prompt_id, exc)
        return False


def search_prompts(query: str, n_results: int = 5) -> dict:
    """Semantic search. Returns an empty result set, with a reason, when unavailable."""
    collection = _get_collection()
    if collection is None:
        return {
            "ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]],
            "unavailable": _unavailable_reason,
        }
    try:
        return collection.query(query_texts=[query], n_results=n_results)
    except Exception as exc:
        logger.warning("semantic search failed: %s", exc)
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]],
                "error": str(exc)}
