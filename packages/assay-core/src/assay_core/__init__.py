"""Assay core.

A plugin-first implementation of the PromptFile v1 specification.

Quick start::

    from assay_core import PromptFile, Runtime

    prompt = PromptFile.load("prompts/support/refund-triage.prompt.md")
    result = Runtime().run(prompt, {"message": "I want my money back"})
    print(result.text, result.cost_usd)

Nothing in this package hardcodes a provider, a template dialect, an evaluator or a
storage backend. Everything is resolved through :mod:`assay_core.registry`.
"""

from __future__ import annotations

__version__ = "1.0.0"
__spec_version__ = 1

from .catalog import ModelCatalog, parse_model_ref
from .contracts import (
    CONTRACT_VERSION,
    Budget,
    AsyncProvider,
    Completion,
    ContextStrategy,
    Controller,
    CycleResult,
    EvalResult,
    Evaluator,
    Guardrail,
    GuardrailResult,
    LoopRun,
    Memory,
    MemoryRecord,
    Message,
    ModelInfo,
    Provider,
    StreamingProvider,
    StreamChunk,
    RenderedPrompt,
    Renderer,
    Step,
    Store,
    ToolCall,
    ToolProvider,
    ToolResult,
    Trajectory,
    Usage,
)
from .errors import (
    BudgetExceeded,
    CapabilityError,
    GuardrailViolation,
    HarnessError,
    LoopError,
    OptimizationError,
    AssayError,
    NotFound,
    PluginNotFound,
    ProviderError,
    RenderError,
    UnsupportedSpecVersion,
    ValidationError,
    VerificationFailed,
)
from . import calibration, disclosure, environment, governance, provenance, redteam, stats
from .harness import AgentRuntime
from .loop import LoopRuntime
from .promptfile import PromptFile, discover, load_schema
from .registry import Registry, get_registry, set_registry
from .runtime import Runtime, RunResult, StreamEvent
from .workspace import Workspace

__all__ = [
    "__version__",
    "__spec_version__",
    "CONTRACT_VERSION",
    # document model
    "PromptFile",
    "discover",
    "load_schema",
    # runtime
    "Runtime",
    "RunResult",
    "StreamEvent",
    "Workspace",
    # harness and loop
    "AgentRuntime",
    "LoopRuntime",
    "disclosure",
    "provenance",
    "calibration",
    "environment",
    "governance",
    "redteam",
    "stats",
    "Trajectory",
    "Step",
    "ToolCall",
    "ToolResult",
    "Budget",
    "CycleResult",
    "LoopRun",
    # plugins
    "Registry",
    "get_registry",
    "set_registry",
    "Renderer",
    "Provider",
    "AsyncProvider",
    "StreamingProvider",
    "Evaluator",
    "Guardrail",
    "Store",
    "Memory",
    "MemoryRecord",
    "ToolProvider",
    "ContextStrategy",
    "Controller",
    # values
    "Message",
    "RenderedPrompt",
    "Completion",
    "StreamChunk",
    "Usage",
    "ModelInfo",
    "EvalResult",
    "GuardrailResult",
    "ModelCatalog",
    "parse_model_ref",
    # errors
    "AssayError",
    "ValidationError",
    "UnsupportedSpecVersion",
    "RenderError",
    "ProviderError",
    "CapabilityError",
    "GuardrailViolation",
    "PluginNotFound",
    "NotFound",
    "HarnessError",
    "BudgetExceeded",
    "LoopError",
    "OptimizationError",
    "VerificationFailed",
]
