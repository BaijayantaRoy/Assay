"""Built-in renderers (``assay.renderers``).

Adding a new template dialect means shipping a class with ``render`` and
``variables_of`` and one entry-point line. Core is never edited.
"""

from __future__ import annotations

import re
import string
from typing import Any

from ..contracts import CONTRACT_VERSION
from ..errors import RenderError


class Jinja2Renderer:
    """Default dialect. Sandboxed: no attribute access to dunder members, no eval."""

    id = "jinja2"
    contract_version = CONTRACT_VERSION

    def __init__(self) -> None:
        from jinja2 import StrictUndefined, Undefined
        from jinja2.sandbox import SandboxedEnvironment

        self._strict_env = SandboxedEnvironment(
            undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True,
            keep_trailing_newline=True, autoescape=False,
        )
        self._lax_env = SandboxedEnvironment(
            undefined=Undefined, trim_blocks=True, lstrip_blocks=True,
            keep_trailing_newline=True, autoescape=False,
        )

    def render(self, template: str, variables: dict[str, Any], *, strict: bool = True) -> str:
        from jinja2 import TemplateError

        env = self._strict_env if strict else self._lax_env
        try:
            return env.from_string(template).render(**variables)
        except TemplateError as exc:
            raise RenderError(
                f"Jinja2 render failed: {exc}", renderer=self.id, strict=strict
            ) from exc

    def variables_of(self, template: str) -> set[str]:
        from jinja2 import TemplateError, meta

        try:
            ast = self._strict_env.parse(template)
            return set(meta.find_undeclared_variables(ast))
        except TemplateError as exc:
            raise RenderError(
                f"Jinja2 template parse failed: {exc}", renderer=self.id
            ) from exc


class FStringRenderer:
    """``{name}`` substitution. Cheap, dependency-free, no logic."""

    id = "fstring"
    contract_version = CONTRACT_VERSION

    def render(self, template: str, variables: dict[str, Any], *, strict: bool = True) -> str:
        try:
            if strict:
                return template.format(**variables)
            return string.Formatter().vformat(template, (), _Defaulting(variables))
        except (KeyError, IndexError) as exc:
            raise RenderError(f"Missing variable {exc}", renderer=self.id) from exc

    def variables_of(self, template: str) -> set[str]:
        found = set()
        for _, field_name, _, _ in string.Formatter().parse(template):
            if field_name:
                found.add(field_name.split(".")[0].split("[")[0])
        return found


class _Defaulting(dict):
    def __missing__(self, key):  # pragma: no cover - trivial
        return ""


class PassthroughRenderer:
    """No templating at all. For prompts whose braces are literal content."""

    id = "none"
    contract_version = CONTRACT_VERSION

    def render(self, template: str, variables: dict[str, Any], *, strict: bool = True) -> str:
        return template

    def variables_of(self, template: str) -> set[str]:
        return set()


class MustacheRenderer:
    """Minimal ``{{ name }}`` substitution — the dotprompt/Handlebars subset.

    Not registered by default; ships as an example of a drop-in third-party renderer.
    """

    id = "mustache"
    contract_version = CONTRACT_VERSION
    _var = re.compile(r"\{\{\s*([a-zA-Z_][\w.]*)\s*\}\}")

    def render(self, template: str, variables: dict[str, Any], *, strict: bool = True) -> str:
        def sub(match: re.Match) -> str:
            key = match.group(1)
            cursor: Any = variables
            for part in key.split("."):
                if isinstance(cursor, dict) and part in cursor:
                    cursor = cursor[part]
                else:
                    if strict:
                        raise RenderError(f"Undefined variable {key!r}", renderer=self.id)
                    return ""
            return str(cursor)

        return self._var.sub(sub, template)

    def variables_of(self, template: str) -> set[str]:
        return {m.group(1).split(".")[0] for m in self._var.finditer(template)}
