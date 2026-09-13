"""Plugin registry with entry-point discovery.

Three ways a plugin reaches the registry, in increasing precedence:

1. **Entry points** — any installed distribution advertising ``assay.*`` groups.
   Built-ins use this path too; there is no privileged registration.
2. **Workspace config** — ``plugins:`` in ``assay.yaml`` (module paths or pins).
3. **Programmatic** — :meth:`Registry.register`, for tests and embedding.

Discovery is lazy and failure-isolated: one broken plugin degrades to a recorded
load error, never an import-time crash of the whole process.
"""

from __future__ import annotations

import importlib
import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Iterator

from .contracts import CONTRACT_GROUPS, CONTRACT_VERSION
from .errors import IncompatiblePlugin, PluginLoadError, PluginNotFound

logger = logging.getLogger("assay.registry")

try:  # Python 3.10+ stdlib; the selectable API landed in 3.10
    from importlib.metadata import entry_points
except ImportError:  # pragma: no cover
    entry_points = None  # type: ignore[assignment]


def _major(version: str) -> str:
    return str(version).split(".", 1)[0]


@dataclass(slots=True)
class PluginRecord:
    """One resolved (or failed) plugin."""

    name: str
    group: str
    source: str  # "entry_point" | "config" | "programmatic"
    target: str = ""
    instance: Any = None
    error: str | None = None
    distribution: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class Registry:
    """Resolves plugin names to instances for a given contract group.

    The registry is deliberately dumb about *what* plugins do — it only enforces
    contract-version compatibility and structural conformance to the Protocol.
    """

    def __init__(self, *, autoload: bool = True, extra: dict[str, dict[str, Any]] | None = None):
        self._records: dict[str, dict[str, PluginRecord]] = {g: {} for g in CONTRACT_GROUPS}
        self._scanned = False
        self._scan_lock = threading.RLock()
        self._autoload = autoload
        if extra:
            for group, mapping in extra.items():
                for name, target in mapping.items():
                    self.register_path(group, name, target, source="config")

    # -- discovery ---------------------------------------------------------

    def scan(self, *, force: bool = False) -> None:
        """Populate the registry from installed entry points. Idempotent."""
        with self._scan_lock:
            if self._scanned and not force:
                return
            if not self._autoload:
                # Scoped registries (for example one isolated red-team attack) are
                # populated explicitly. Re-scanning every installed distribution for
                # each scope is both incorrect and prohibitively expensive on Windows.
                self._scanned = True
                return
            if entry_points is None or os.environ.get("ASSAY_NO_ENTRYPOINTS"):
                self._register_builtins_directly()
                self._scanned = True
                return

            for group in CONTRACT_GROUPS:
                try:
                    eps = entry_points(group=group)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug("entry point scan failed for %s: %s", group, exc)
                    continue
                for ep in eps:
                    dist = getattr(getattr(ep, "dist", None), "name", None)
                    rec = PluginRecord(
                        name=ep.name, group=group, source="entry_point",
                        target=ep.value, distribution=dist,
                    )
                    self._records[group].setdefault(ep.name, rec)

            # Fill any missing built-ins from the running source tree. ``setdefault`` keeps
            # installed entry points authoritative while allowing a source checkout to add a
            # new built-in before editable-install metadata has been refreshed.
            self._register_builtins_directly()
            # Publish completion only after all groups and built-in fallbacks are visible.
            self._scanned = True

    def _register_builtins_directly(self) -> None:
        """Fallback registration so core works before `pip install -e`."""
        builtins: dict[str, dict[str, str]] = {
            "assay.renderers": {
                "jinja2": "assay_core.builtins.renderers:Jinja2Renderer",
                "fstring": "assay_core.builtins.renderers:FStringRenderer",
                "none": "assay_core.builtins.renderers:PassthroughRenderer",
            },
            "assay.providers": {
                "openai": "assay_core.builtins.providers:OpenAIProvider",
                "anthropic": "assay_core.builtins.providers:AnthropicProvider",
                "google": "assay_core.builtins.providers:GoogleProvider",
                "ollama": "assay_core.builtins.providers:OllamaProvider",
                "openai_compatible": "assay_core.builtins.providers:OpenAICompatibleProvider",
                "echo": "assay_core.builtins.providers:EchoProvider",
            },
            "assay.evaluators": {
                "contains": "assay_core.builtins.evaluators:ContainsEvaluator",
                "not_contains": "assay_core.builtins.evaluators:NotContainsEvaluator",
                "equals": "assay_core.builtins.evaluators:EqualsEvaluator",
                "regex": "assay_core.builtins.evaluators:RegexEvaluator",
                "json_valid": "assay_core.builtins.evaluators:JsonValidEvaluator",
                "json_schema": "assay_core.builtins.evaluators:JsonSchemaEvaluator",
                "cost_under": "assay_core.builtins.evaluators:CostUnderEvaluator",
                "latency_under": "assay_core.builtins.evaluators:LatencyUnderEvaluator",
                "llm_judge": "assay_core.builtins.evaluators:LLMJudgeEvaluator",
                "tool_called": "assay_core.builtins.trajectory:ToolCalledEvaluator",
                "tool_not_called": "assay_core.builtins.trajectory:ToolNotCalledEvaluator",
                "tool_call_order": "assay_core.builtins.trajectory:ToolCallOrderEvaluator",
                "trajectory_accuracy": "assay_core.builtins.trajectory:TrajectoryAccuracyEvaluator",
                "no_repeated_tool_call": "assay_core.builtins.trajectory:NoRepeatedToolCallEvaluator",
                "iterations_under": "assay_core.builtins.trajectory:IterationsUnderEvaluator",
                "tool_calls_under": "assay_core.builtins.trajectory:ToolCallsUnderEvaluator",
                "budget_under": "assay_core.builtins.trajectory:BudgetUnderEvaluator",
                "no_tool_errors": "assay_core.builtins.trajectory:NoToolErrorsEvaluator",
                "no_denied_calls": "assay_core.builtins.trajectory:NoDeniedCallsEvaluator",
                "completed": "assay_core.builtins.trajectory:CompletedEvaluator",
                "verified": "assay_core.builtins.trajectory:VerifiedEvaluator",
                "no_injection_compliance": "assay_core.builtins.trajectory:NoInjectionComplianceEvaluator",
                "injection_detected": "assay_core.builtins.trajectory:InjectionDetectedEvaluator",
                "cycles_under": "assay_core.builtins.trajectory:CyclesUnderEvaluator",
                "goal_met": "assay_core.builtins.trajectory:GoalMetEvaluator",
                "steps_verified": "assay_core.builtins.trajectory:StepsVerifiedEvaluator",
                "memory_recalled": "assay_core.builtins.trajectory:MemoryRecalledEvaluator",
                "memory_written": "assay_core.builtins.trajectory:MemoryWrittenEvaluator",
            },
            "assay.guardrails": {
                "regex_block": "assay_core.builtins.guardrails:RegexBlockGuardrail",
                "max_length": "assay_core.builtins.guardrails:MaxLengthGuardrail",
                "pii": "assay_core.builtins.guardrails:PIIGuardrail",
                "schema": "assay_core.builtins.guardrails:SchemaGuardrail",
                "injection": "assay_core.builtins.guardrails:InjectionGuardrail",
            },
            "assay.stores": {"file": "assay_core.builtins.stores:FileStore"},
            "assay.importers": {
                "promptfoo": "assay_core.builtins.importers:PromptfooImporter",
                "messages": "assay_core.builtins.importers:MessagesImporter",
                "dotprompt": "assay_core.builtins.importers:DotpromptImporter",
                "poml": "assay_core.builtins.importers:PomlImporter",
                "langfuse": "assay_core.builtins.importers:LangfuseImporter",
                "promptlayer": "assay_core.builtins.importers:PromptLayerImporter",
            },
            "assay.tracers": {
                "opentelemetry": "assay_core.builtins.tracers:OpenTelemetryTracer",
            },
            "assay.optimizers": {
                "reflective": "assay_core.builtins.optimizers:ReflectiveRewriteOptimizer",
            },
            "assay.tools": {
                "fs": "assay_core.builtins.tools:FileSystemTools",
                "shell": "assay_core.builtins.tools:ShellTools",
                "http": "assay_core.builtins.tools:HttpTools",
                "prompt": "assay_core.builtins.tools:PromptTools",
                "mock": "assay_core.builtins.tools:MockTools",
            },
            "assay.context": {
                "none": "assay_core.builtins.context:NoContextStrategy",
                "truncate": "assay_core.builtins.context:TruncateContextStrategy",
                "selective_clear": "assay_core.builtins.context:SelectiveClearContextStrategy",
                "compact": "assay_core.builtins.context:CompactContextStrategy",
                "summarize": "assay_core.builtins.context:SummarizeContextStrategy",
            },
            "assay.memory": {
                "jsonl": "assay_core.builtins.memory:JsonlMemory",
                "memory": "assay_core.builtins.memory:InMemoryMemory",
                "null": "assay_core.builtins.memory:NullMemory",
            },
            "assay.controllers": {
                "policy": "assay_core.builtins.controllers:PolicyController",
                "read_only": "assay_core.builtins.controllers:ReadOnlyController",
            },
        }
        for group, mapping in builtins.items():
            for name, target in mapping.items():
                self._records[group].setdefault(
                    name,
                    PluginRecord(name=name, group=group, source="entry_point", target=target),
                )

    # -- registration ------------------------------------------------------

    def register(self, group: str, name: str, instance: Any) -> None:
        """Register an already-constructed plugin instance."""
        self._check_group(group)
        self._verify(group, name, instance)
        self._records[group][name] = PluginRecord(
            name=name, group=group, source="programmatic", instance=instance,
            target=type(instance).__module__ + ":" + type(instance).__qualname__,
        )

    def register_path(self, group: str, name: str, target: str, *, source: str = "config") -> None:
        """Register by ``module:Attribute`` path, resolved lazily."""
        self._check_group(group)
        self._records[group][name] = PluginRecord(
            name=name, group=group, source=source, target=target
        )

    # -- resolution --------------------------------------------------------

    def get(self, group: str, name: str) -> Any:
        """Return a plugin instance, loading it on first use."""
        self._check_group(group)
        self.scan()
        rec = self._records[group].get(name)
        if rec is None:
            available = sorted(self._records[group])
            raise PluginNotFound(
                f"No {group.split('.')[-1][:-1]} named {name!r}",
                group=group, name=name, available=available,
            )
        if rec.instance is None:
            rec.instance = self._load(rec)
        return rec.instance

    def has(self, group: str, name: str) -> bool:
        self.scan()
        return name in self._records.get(group, {})

    def names(self, group: str) -> list[str]:
        self._check_group(group)
        self.scan()
        return sorted(self._records[group])

    def records(self, group: str | None = None) -> Iterator[PluginRecord]:
        self.scan()
        groups = [group] if group else list(self._records)
        for g in groups:
            yield from self._records[g].values()

    def describe(self) -> dict[str, list[dict]]:
        """Machine-readable inventory. Backs ``assay plugins list`` and ``GET /v1/plugins``."""
        self.scan()
        out: dict[str, list[dict]] = {}
        for group, mapping in self._records.items():
            out[group] = [
                {
                    "name": r.name,
                    "target": r.target,
                    "source": r.source,
                    "distribution": r.distribution,
                    "loaded": r.instance is not None,
                    "error": r.error,
                }
                for r in sorted(mapping.values(), key=lambda r: r.name)
            ]
        return out

    # -- internals ---------------------------------------------------------

    def _check_group(self, group: str) -> None:
        if group not in CONTRACT_GROUPS:
            raise PluginNotFound(
                f"Unknown plugin group {group!r}", known=sorted(CONTRACT_GROUPS)
            )

    def _load(self, rec: PluginRecord) -> Any:
        try:
            module_path, _, attr = rec.target.partition(":")
            module = importlib.import_module(module_path)
            obj = getattr(module, attr) if attr else module
            instance = obj() if isinstance(obj, type) else obj
        except Exception as exc:
            rec.error = f"{type(exc).__name__}: {exc}"
            raise PluginLoadError(
                f"Failed to load plugin {rec.name!r} from {rec.target!r}",
                group=rec.group, name=rec.name, cause=rec.error,
            ) from exc
        self._verify(rec.group, rec.name, instance)
        return instance

    def _verify(self, group: str, name: str, instance: Any) -> None:
        declared = getattr(instance, "contract_version", None)
        if declared is None:
            raise IncompatiblePlugin(
                f"Plugin {name!r} does not declare contract_version",
                group=group, name=name,
            )
        if _major(declared) != _major(CONTRACT_VERSION):
            raise IncompatiblePlugin(
                f"Plugin {name!r} targets contract {declared}, core implements {CONTRACT_VERSION}",
                group=group, name=name, plugin_contract=declared, core_contract=CONTRACT_VERSION,
            )
        protocol = CONTRACT_GROUPS[group]
        if not isinstance(instance, protocol):
            raise IncompatiblePlugin(
                f"Plugin {name!r} does not satisfy the {protocol.__name__} contract",
                group=group, name=name,
            )


_default: Registry | None = None
_default_lock = threading.Lock()


def get_registry() -> Registry:
    """Process-wide default registry."""
    global _default
    if _default is None:
        with _default_lock:
            if _default is None:
                _default = Registry()
    return _default


def set_registry(registry: Registry | None) -> None:
    """Replace the default registry. Primarily for tests and embedding."""
    global _default
    _default = registry
