"""Error taxonomy.

Every error carries a stable, machine-readable ``code``. Codes are part of the public
API surface: they may be added, never repurposed. Tooling (CLI exit codes, API error
bodies, MCP error payloads) maps onto these.
"""

from __future__ import annotations

from typing import Any


class AssayError(Exception):
    """Base for everything this library raises."""

    code = "assay.error"

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context = context

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "context": self.context}

    def __str__(self) -> str:  # pragma: no cover - trivial
        if self.context:
            extras = " ".join(f"{k}={v!r}" for k, v in self.context.items())
            return f"{self.message} ({extras})"
        return self.message


# --- spec / parsing -------------------------------------------------------


class SpecError(AssayError):
    code = "assay.spec"


class UnsupportedSpecVersion(SpecError):
    """The file declares a ``promptfile:`` major version this build does not implement.

    Per the conformance rules we refuse rather than guess.
    """

    code = "assay.spec.unsupported_version"


class ValidationError(SpecError):
    code = "assay.spec.validation"

    def __init__(self, message: str, errors: list[str] | None = None, **context: Any) -> None:
        super().__init__(message, **context)
        self.errors = errors or []

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["errors"] = self.errors
        return d


class ParseError(SpecError):
    code = "assay.spec.parse"


# --- plugins --------------------------------------------------------------


class PluginError(AssayError):
    code = "assay.plugin"


class PluginNotFound(PluginError):
    code = "assay.plugin.not_found"


class PluginLoadError(PluginError):
    code = "assay.plugin.load_failed"


class IncompatiblePlugin(PluginError):
    """Plugin implements a contract version this build cannot talk to."""

    code = "assay.plugin.incompatible"


# --- runtime --------------------------------------------------------------


class RenderError(AssayError):
    code = "assay.render"


class CapabilityError(AssayError):
    """``requires.capabilities`` cannot be satisfied. Fail closed, never degrade."""

    code = "assay.runtime.capability_unmet"


class ProviderError(AssayError):
    code = "assay.provider"


class AuthError(ProviderError):
    code = "assay.provider.auth"


class RateLimitError(ProviderError):
    code = "assay.provider.rate_limit"


class GuardrailViolation(AssayError):
    code = "assay.guardrail.violation"


class OptimizationError(AssayError):
    code = "assay.optimizer"


# --- harness / loop -------------------------------------------------------


class HarnessError(AssayError):
    """Structural problem with a harness definition — a missing tool provider,
    an unavailable controller, an unknown context strategy."""

    code = "assay.harness"


class BudgetExceeded(AssayError):
    """A run hit a hard ceiling. Carries the trajectory so partial work is not lost."""

    code = "assay.harness.budget_exceeded"


class LoopError(AssayError):
    code = "assay.loop"


class VerificationFailed(LoopError):
    """The loop's verification step did not pass.

    Distinct from a generic failure: the agent claimed success and the check disagreed,
    which is the single most valuable signal a loop produces.
    """

    code = "assay.loop.verification_failed"


class StoreError(AssayError):
    code = "assay.store"


class NotFound(StoreError):
    code = "assay.store.not_found"
