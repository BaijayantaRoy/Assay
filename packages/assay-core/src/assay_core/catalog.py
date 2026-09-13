"""Model catalogue.

Model ids, context windows, capabilities and prices change weekly. Hardcoding them
into provider code guarantees the project rots. Instead the catalogue is *data*,
loaded in priority order:

1. ``$ASSAY_MODEL_CATALOG`` — an explicit JSON file.
2. ``<workspace>/models.json`` — workspace-local overrides, committed to git.
3. ``~/.assay/models.json`` — user cache, refreshed by ``assay models sync``.
4. The bundled seed catalogue below.

Later sources never overwrite earlier ones. Unknown models resolve to ``None`` and
degrade to zero-cost rather than raising: an unpriced model must still be runnable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

from .contracts import ModelInfo

#: Minimal offline seed. Deliberately small — ``assay models sync`` is the real source.
#: Prices are USD per million tokens.
SEED_CATALOG: list[dict] = [
    {"id": "echo", "provider": "echo", "display_name": "Echo (offline)",
     "context_window": 1000000, "capabilities": ["text", "json_mode", "tools"]},
    {"id": "gpt-4o", "provider": "openai", "display_name": "GPT-4o",
     "context_window": 128000, "max_output_tokens": 16384,
     "input_cost_per_mtok": 2.5, "output_cost_per_mtok": 10.0,
     "cached_input_cost_per_mtok": 1.25,
     "capabilities": ["text", "tools", "vision", "json_mode", "streaming"]},
    {"id": "gpt-4o-mini", "provider": "openai", "display_name": "GPT-4o mini",
     "context_window": 128000, "max_output_tokens": 16384,
     "input_cost_per_mtok": 0.15, "output_cost_per_mtok": 0.6,
     "capabilities": ["text", "tools", "vision", "json_mode", "streaming"]},
    {"id": "claude-opus-4", "provider": "anthropic", "display_name": "Claude Opus 4",
     "context_window": 200000, "max_output_tokens": 32000,
     "input_cost_per_mtok": 15.0, "output_cost_per_mtok": 75.0,
     "cached_input_cost_per_mtok": 1.5,
     "capabilities": ["text", "tools", "vision", "streaming", "cache_control", "reasoning"]},
    {"id": "claude-sonnet-4", "provider": "anthropic", "display_name": "Claude Sonnet 4",
     "context_window": 200000, "max_output_tokens": 64000,
     "input_cost_per_mtok": 3.0, "output_cost_per_mtok": 15.0,
     "cached_input_cost_per_mtok": 0.3,
     "capabilities": ["text", "tools", "vision", "streaming", "cache_control", "reasoning"]},
    {"id": "gemini-2.5-pro", "provider": "google", "display_name": "Gemini 2.5 Pro",
     "context_window": 1000000, "max_output_tokens": 65536,
     "input_cost_per_mtok": 1.25, "output_cost_per_mtok": 10.0,
     "capabilities": ["text", "tools", "vision", "json_mode", "streaming"]},
    {"id": "gemini-2.5-flash", "provider": "google", "display_name": "Gemini 2.5 Flash",
     "context_window": 1000000, "max_output_tokens": 65536,
     "input_cost_per_mtok": 0.3, "output_cost_per_mtok": 2.5,
     "capabilities": ["text", "tools", "vision", "json_mode", "streaming"]},
]


def _user_catalog_path() -> Path:
    root = os.getenv("ASSAY_HOME") or str(Path.home() / ".assay")
    return Path(root) / "models.json"


class ModelCatalog:
    """Keyed by canonical ``provider/model`` reference."""

    _default: "ModelCatalog | None" = None

    def __init__(self, entries: Iterable[dict] | None = None) -> None:
        self._models: dict[str, ModelInfo] = {}
        for entry in entries or []:
            self.add(entry)

    # -- construction ------------------------------------------------------

    @classmethod
    def default(cls) -> "ModelCatalog":
        if cls._default is None:
            cls._default = cls.autoload()
        return cls._default

    @classmethod
    def reset(cls) -> None:
        cls._default = None

    @classmethod
    def autoload(cls, workspace: Path | None = None) -> "ModelCatalog":
        catalog = cls()
        sources: list[Path] = []
        if env_path := os.getenv("ASSAY_MODEL_CATALOG"):
            sources.append(Path(env_path))
        if workspace:
            sources.append(Path(workspace) / "models.json")
        sources.append(_user_catalog_path())

        for source in sources:
            try:
                if source.is_file():
                    payload = json.loads(source.read_text(encoding="utf-8"))
                    for entry in payload.get("models", payload if isinstance(payload, list) else []):
                        catalog.add(entry, overwrite=False)
            except Exception:
                continue  # a malformed override must never break execution

        for entry in SEED_CATALOG:
            catalog.add(entry, overwrite=False)
        return catalog

    # -- access ------------------------------------------------------------

    def add(self, entry: dict, *, overwrite: bool = True) -> None:
        provider = entry.get("provider", "")
        model_id = entry.get("id", "")
        if not provider or not model_id:
            return
        key = f"{provider}/{model_id}"
        if not overwrite and key in self._models:
            return
        known = {
            "id", "provider", "display_name", "context_window", "max_output_tokens",
            "input_cost_per_mtok", "output_cost_per_mtok", "cached_input_cost_per_mtok",
            "capabilities", "deprecated",
        }
        self._models[key] = ModelInfo(
            id=model_id,
            provider=provider,
            display_name=entry.get("display_name") or model_id,
            context_window=int(entry.get("context_window") or 0),
            max_output_tokens=int(entry.get("max_output_tokens") or 0),
            input_cost_per_mtok=float(entry.get("input_cost_per_mtok") or 0.0),
            output_cost_per_mtok=float(entry.get("output_cost_per_mtok") or 0.0),
            cached_input_cost_per_mtok=float(entry.get("cached_input_cost_per_mtok") or 0.0),
            capabilities=frozenset(entry.get("capabilities") or []),
            deprecated=bool(entry.get("deprecated")),
            extra={k: v for k, v in entry.items() if k not in known},
        )

    def get(self, ref: str) -> ModelInfo | None:
        """``ref`` is ``provider/model``; a bare model id is matched across providers."""
        if ref in self._models:
            return self._models[ref]
        if "/" not in ref:
            for key, info in self._models.items():
                if key.split("/", 1)[1] == ref:
                    return info
        return None

    def by_provider(self, provider: str) -> list[ModelInfo]:
        return [m for m in self._models.values() if m.provider == provider]

    def all(self) -> list[ModelInfo]:
        return list(self._models.values())

    def providers(self) -> list[str]:
        return sorted({m.provider for m in self._models.values()})

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._models)


def parse_model_ref(ref: str, *, default_provider: str = "openai") -> tuple[str, str]:
    """Split ``provider/model`` into its parts, inferring the provider when absent.

    Inference is a convenience only; ambiguity is resolved in favour of an explicit
    catalogue entry, then heuristics, then ``default_provider``.
    """
    if "/" in ref:
        provider, model = ref.split("/", 1)
        # ``ollama/llama3.3:8b`` and ``openai_compatible/org/model`` both work.
        return provider, model

    info = ModelCatalog.default().get(ref)
    if info:
        return info.provider, info.id

    heuristics = (
        ("claude", "anthropic"), ("gpt-", "openai"), ("o1", "openai"), ("o3", "openai"),
        ("o4", "openai"), ("gemini", "google"), ("gemma", "google"),
        ("deepseek", "openai_compatible"), ("qwen", "openai_compatible"),
        ("mistral", "openai_compatible"), ("llama", "ollama"), ("echo", "echo"),
    )
    lowered = ref.lower()
    for needle, provider in heuristics:
        if lowered.startswith(needle):
            return provider, ref
    return default_provider, ref
