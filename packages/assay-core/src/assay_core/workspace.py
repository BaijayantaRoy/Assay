"""Workspace configuration — ``assay.yaml``.

One file at the root of a prompt repository. Everything in it is optional; a bare
directory of ``.prompt.md`` files is already a valid workspace.

```yaml
promptfile: 1
name: acme-prompts
prompts: ./prompts            # root to scan
store: file                   # store plugin id
defaults:
  model: anthropic/claude-opus-5-5
  params: { temperature: 0.2 }
  renderer: jinja2
providers:
  openai_compatible:
    base_url: https://api.groq.com/openai/v1
    api_key_env: GROQ_API_KEY
plugins:                      # extra plugins beyond installed entry points
  assay.evaluators:
    house_style: acme_evals:HouseStyleEvaluator
tracing:
  enabled: true
  exporter: otlp
policy:                       # enforced by `assay lint --policy` and CI
  require_evals_for: [stable]
  forbid_status: [archived]
  max_cost_per_run_usd: 0.50
```
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_NAMES = ("assay.yaml", "assay.yml", ".assay.yaml")


@dataclass
class Workspace:
    root: Path
    config: dict[str, Any] = field(default_factory=dict)
    config_path: Path | None = None

    # -- discovery ---------------------------------------------------------

    @classmethod
    def find(cls, start: str | Path | None = None) -> "Workspace":
        """Walk upward from ``start`` looking for a config file; fall back to cwd."""
        cursor = Path(start or os.getcwd()).resolve()
        for candidate in [cursor, *cursor.parents]:
            for name in CONFIG_NAMES:
                path = candidate / name
                if path.is_file():
                    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                    return cls(root=candidate, config=data, config_path=path)
        return cls(root=cursor, config={})

    @classmethod
    def init(cls, root: str | Path, *, name: str | None = None) -> "Workspace":
        base = Path(root).resolve()
        base.mkdir(parents=True, exist_ok=True)
        path = base / "assay.yaml"
        config = {
            "promptfile":  1,
            "name": name or base.name,
            "prompts": "./prompts",
            "defaults": {"model": "echo/echo", "renderer": "jinja2"},
        }
        if not path.exists():
            path.write_text(
                yaml.dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
        (base / "prompts").mkdir(exist_ok=True)
        return cls(root=base, config=config, config_path=path)

    # -- accessors ---------------------------------------------------------

    @property
    def name(self) -> str:
        return self.config.get("name") or self.root.name

    @property
    def prompts_root(self) -> Path:
        rel = self.config.get("prompts", ".")
        path = (self.root / rel).resolve()
        return path if path.exists() else self.root

    @property
    def store_id(self) -> str:
        return self.config.get("store", "file")

    @property
    def defaults(self) -> dict[str, Any]:
        return dict(self.config.get("defaults") or {})

    @property
    def default_model(self) -> str | None:
        return os.getenv("ASSAY_DEFAULT_MODEL") or self.defaults.get("model")

    @property
    def default_params(self) -> dict[str, Any]:
        return dict(self.defaults.get("params") or {})

    @property
    def provider_config(self) -> dict[str, dict]:
        return dict(self.config.get("providers") or {})

    @property
    def plugin_config(self) -> dict[str, dict[str, str]]:
        return dict(self.config.get("plugins") or {})

    @property
    def policy(self) -> dict[str, Any]:
        return dict(self.config.get("policy") or {})

    @property
    def tracing(self) -> dict[str, Any]:
        return dict(self.config.get("tracing") or {})

    @property
    def is_initialised(self) -> bool:
        return self.config_path is not None

    # -- wiring ------------------------------------------------------------

    def registry(self):
        """A registry pre-seeded with this workspace's extra plugins."""
        from .registry import Registry

        return Registry(extra=self.plugin_config)

    def store(self):
        """The configured store, constructed against this workspace's prompt root."""
        from .builtins.stores import FileStore

        if self.store_id == "file":
            return FileStore(self.prompts_root)
        return self.registry().get("assay.stores", self.store_id)

    def save(self) -> Path:
        path = self.config_path or (self.root / "assay.yaml")
        path.write_text(
            yaml.dump(self.config, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        self.config_path = path
        return path
