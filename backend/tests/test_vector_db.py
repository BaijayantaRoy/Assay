"""Regression contracts for the optional native vector-search integration."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from backend.services import vector_db


class NativeExtensionPanic(BaseException):
    """Models pyo3's PanicException, which intentionally bypasses Exception."""


def _install_failing_chromadb(monkeypatch: pytest.MonkeyPatch, error: BaseException) -> None:
    chromadb = ModuleType("chromadb")
    chromadb.PersistentClient = lambda **_kwargs: (_ for _ in ()).throw(error)  # type: ignore[attr-defined]
    utils = ModuleType("chromadb.utils")
    utils.embedding_functions = SimpleNamespace(DefaultEmbeddingFunction=lambda: object())  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "chromadb", chromadb)
    monkeypatch.setitem(sys.modules, "chromadb.utils", utils)
    monkeypatch.setattr(vector_db, "_collection", None)
    monkeypatch.setattr(vector_db, "_unavailable_reason", None)


def test_native_extension_panic_disables_vectors_without_breaking_writes(monkeypatch):
    _install_failing_chromadb(monkeypatch, NativeExtensionPanic("native panic"))

    assert vector_db._get_collection() is None
    assert vector_db.unavailable_reason() == "chromadb failed to initialise (native panic)"


@pytest.mark.parametrize("signal", [KeyboardInterrupt, SystemExit, GeneratorExit])
def test_process_control_signals_are_never_swallowed(monkeypatch, signal):
    _install_failing_chromadb(monkeypatch, signal())

    with pytest.raises(signal):
        vector_db._get_collection()
