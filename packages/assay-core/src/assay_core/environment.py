"""Execution environment fingerprinting.

Why this exists
---------------
Eval scores are not reproducible across infrastructure, and the reason is not the one
most people assume. Temperature 0 plus a fixed seed does **not** give determinism. The
dominant cause is **batch-size dependence of reduction kernels** — batch composition
varies with concurrent load — rather than floating-point non-associativity. Reported
consequences are large: accuracy swings up to 9%, and response lengths differing by
thousands of tokens, from changing GPU count or hardware model alone.

The practical implication is uncomfortable: **a 2% improvement measured on different
infrastructure is not an improvement.** It is noise, and a tool that lets you compare
those two numbers without saying so is helping you draw a false conclusion.

Until now this project documented that caveat and did nothing about it. This module
records what produced a number, so the comparison can be checked rather than assumed.

What is captured, and what is not
---------------------------------
Enough to tell whether two runs are comparable: provider, model, package versions,
Python, OS, and whether inference was local or remote. **Not** captured: hostnames,
usernames, IP addresses, API keys, or anything else identifying — a fingerprint that
cannot safely be attached to a bug report is a fingerprint nobody will share.

See ``docs/architecture/RESEARCH.md`` §3.10.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from dataclasses import dataclass, field
from typing import Any

#: Fields that must match for two runs to be considered comparable. Deliberately narrow:
#: the OS patch level does not change a model's output, but the model or provider does.
COMPARABLE_FIELDS = ("provider", "model", "assay_core", "inference")


@dataclass(slots=True)
class Environment:
    """What produced a result. Safe to publish."""

    provider: str = ""
    model: str = ""
    #: "local" | "remote" | "offline" — offline means the deterministic echo provider.
    inference: str = "unknown"
    assay_core: str = ""
    python: str = ""
    platform_name: str = ""
    #: Only present when a provider reports it; most do not.
    hardware: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        """Short stable hash of the comparability-relevant fields."""
        material = json.dumps(
            {f: getattr(self, f, "") for f in COMPARABLE_FIELDS}, sort_keys=True
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]

    @property
    def deterministic(self) -> bool:
        """Whether repeat runs here are genuinely reproducible.

        Only the offline provider qualifies. Saying so plainly is more useful than
        implying that ``temperature: 0`` bought reproducibility, which it did not.
        """
        return self.inference == "offline"

    def comparable_to(self, other: "Environment") -> tuple[bool, list[str]]:
        """Whether scores from two environments may be compared, and what differs."""
        differences = [
            f"{f}: {getattr(self, f, '')!r} vs {getattr(other, f, '')!r}"
            for f in COMPARABLE_FIELDS
            if getattr(self, f, "") != getattr(other, f, "")
        ]
        return (not differences), differences

    def to_dict(self) -> dict:
        payload = {
            "fingerprint": self.fingerprint,
            "provider": self.provider,
            "model": self.model,
            "inference": self.inference,
            "deterministic": self.deterministic,
            "assay_core": self.assay_core,
            "python": self.python,
            "platform": self.platform_name,
        }
        if self.hardware:
            payload["hardware"] = self.hardware
        if self.extra:
            payload["extra"] = self.extra
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "Environment":
        return cls(
            provider=data.get("provider", ""),
            model=data.get("model", ""),
            inference=data.get("inference", "unknown"),
            assay_core=data.get("assay_core", ""),
            python=data.get("python", ""),
            platform_name=data.get("platform", ""),
            hardware=data.get("hardware", ""),
            extra=data.get("extra") or {},
        )


#: Providers whose inference happens on the caller's own machine.
_LOCAL_PROVIDERS = {"ollama", "openai_compatible"}
_OFFLINE_PROVIDERS = {"echo"}


def _inference_kind(provider: str) -> str:
    if provider in _OFFLINE_PROVIDERS:
        return "offline"
    if provider in _LOCAL_PROVIDERS:
        return "local"
    return "remote"


def capture(provider: str = "", model: str = "", **extra: Any) -> Environment:
    """Snapshot the current execution environment.

    Cheap enough to call on every run. Contains nothing identifying.
    """
    from . import __version__

    return Environment(
        provider=provider,
        model=model,
        inference=_inference_kind(provider),
        assay_core=__version__,
        python=platform.python_version(),
        platform_name=f"{platform.system()}-{platform.machine()}",
        hardware=os.getenv("ASSAY_HARDWARE", ""),
        extra={k: v for k, v in extra.items() if v is not None},
    )


def comparison_warning(baseline: Environment, current: Environment) -> str | None:
    """A message explaining why two results should not be compared, or ``None``.

    Returned rather than raised: refusing to show a comparison is unhelpful; showing it
    with the reason it may be meaningless is not.
    """
    comparable, differences = baseline.comparable_to(current)
    if not comparable:
        return (
            "These results came from different environments, so the difference between "
            "them is not evidence of a change in quality: "
            + "; ".join(differences)
        )
    if not current.deterministic:
        return (
            "Both results came from the same environment, but remote inference is not "
            "bit-reproducible — batch composition varies with concurrent load, and "
            "reported accuracy swings reach 9% from infrastructure alone. Treat small "
            "differences as noise unless the sample is large."
        )
    return None
