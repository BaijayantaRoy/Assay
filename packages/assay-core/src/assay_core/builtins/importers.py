"""Built-in migration importers.

Import is deliberately conservative: Assay translates only semantics it can preserve and
records everything it could not translate as warnings. A foreign assertion must never turn
into an Assay pass merely because its assertion type was unknown.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import string
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import quote, unquote, urlparse

import httpx
import yaml

from ..catalog import parse_model_ref
from ..contracts import CONTRACT_VERSION
from ..errors import ValidationError
from ..promptfile import PromptFile


@dataclass(frozen=True)
class ImportSource:
    """Parsed foreign file plus the location used to resolve safe local references."""

    path: Path
    text: str
    document: Any
    prefix: str = "imported"
    metadata: dict[str, Any] = field(default_factory=dict)


def load_import_source(path: str | Path, *, prefix: str = "imported") -> ImportSource:
    source_path = Path(path).resolve()
    if not source_path.is_file():
        raise ValidationError(f"Import source not found: {path}")
    if source_path.stat().st_size > 10 * 1024 * 1024:
        raise ValidationError("Import sources larger than 10 MiB are refused")
    text = source_path.read_text(encoding="utf-8")
    try:
        if source_path.suffix.lower() in {".prompt", ".poml"}:
            document = text
        else:
            document = json.loads(text) if source_path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValidationError(f"Invalid import source {source_path}: {exc}") from exc
    return ImportSource(path=source_path, text=text, document=document, prefix=prefix)


def _registry_base_url(value: str) -> str:
    parsed = urlparse(value)
    loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise ValidationError("Registry base URLs must use HTTPS (HTTP is allowed for loopback)")
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValidationError("Registry base URL must be an origin without credentials or query data")
    return value.rstrip("/")


def _registry_response(
    client: httpx.Client,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    auth: tuple[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[str, Any]:
    try:
        with client.stream("GET", url, headers=headers, auth=auth, params=params) as response:
            response.raise_for_status()
            declared = response.headers.get("content-length")
            limit = 10 * 1024 * 1024
            if declared:
                try:
                    declared_size = int(declared)
                except ValueError as exc:
                    raise ValidationError("Registry returned an invalid Content-Length") from exc
                if declared_size > limit:
                    raise ValidationError("Registry responses larger than 10 MiB are refused")
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > limit:
                    raise ValidationError("Registry responses larger than 10 MiB are refused")
                chunks.append(chunk)
    except httpx.HTTPStatusError as exc:
        raise ValidationError(
            f"Registry request failed with HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise ValidationError(f"Registry request failed: {exc}") from exc
    text = b"".join(chunks).decode("utf-8")
    try:
        return text, json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError("Registry returned invalid JSON") from exc


def load_registry_source(
    uri: str,
    *,
    prefix: str = "imported",
    label: str | None = None,
    version: int | None = None,
    base_url: str | None = None,
    environ: Mapping[str, str] | None = None,
    client: httpx.Client | None = None,
) -> ImportSource:
    """Fetch one immutable registry response without persisting its credentials.

    Supported forms are ``langfuse://prompt-name`` and
    ``promptlayer://prompt-name``. Credentials are read only from the corresponding
    environment variables; they never enter the returned document or PromptFile.
    """
    parsed = urlparse(uri)
    registry = parsed.scheme.lower()
    if registry not in {"langfuse", "promptlayer"}:
        raise ValidationError("Remote imports require langfuse:// or promptlayer://")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValidationError("Registry import URIs may not contain credentials or query data")
    identifier = unquote((parsed.netloc + parsed.path).strip("/"))
    if not identifier:
        raise ValidationError("Registry import URI must name a prompt")
    if label is not None and version is not None:
        raise ValidationError("Registry label and version selectors are mutually exclusive")
    env = environ if environ is not None else os.environ
    params: dict[str, Any] = {}
    if label is not None:
        params["label"] = label
    if version is not None:
        params["version"] = version

    if registry == "langfuse":
        public_key = env.get("LANGFUSE_PUBLIC_KEY")
        secret_key = env.get("LANGFUSE_SECRET_KEY")
        if not public_key or not secret_key:
            raise ValidationError(
                "Langfuse import requires LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY"
            )
        origin = _registry_base_url(
            base_url or env.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
        )
        url = f"{origin}/api/public/v2/prompts/{quote(identifier, safe='')}"
        request_kwargs = {"auth": (public_key, secret_key), "params": params}
    else:
        api_key = env.get("PROMPTLAYER_API_KEY")
        if not api_key:
            raise ValidationError("PromptLayer import requires PROMPTLAYER_API_KEY")
        origin = _registry_base_url(
            base_url or env.get("PROMPTLAYER_BASE_URL", "https://api.promptlayer.com")
        )
        url = f"{origin}/prompt-templates/{quote(identifier, safe='')}"
        request_kwargs = {"headers": {"X-API-KEY": api_key}, "params": params}

    if client is None:
        with httpx.Client(timeout=20.0, follow_redirects=False) as owned_client:
            text, document = _registry_response(owned_client, url, **request_kwargs)
    else:
        text, document = _registry_response(client, url, **request_kwargs)
    safe_request = {"registry": registry, "identifier": identifier}
    if label is not None:
        safe_request["label"] = label
    if version is not None:
        safe_request["version"] = version
    return ImportSource(
        path=Path(f"{registry}-{_slug(identifier)}.json").resolve(),
        text=text,
        document=document,
        prefix=prefix,
        metadata={"source_uri": uri, "registry_request": safe_request},
    )


def _unwrap(data: Any) -> tuple[Any, Path | None, str]:
    if isinstance(data, ImportSource):
        return data.document, data.path, data.prefix
    return data, None, "imported"


def _slug(value: Any, fallback: str = "prompt") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text).strip("-._")
    return text or fallback


def _safe_file(base: Path, reference: str) -> Path:
    raw = reference.removeprefix("file://").split(":", 1)[0]
    if any(mark in raw for mark in ("*", "?", "[")):
        raise ValidationError(f"Globbed import references are not executed: {reference}")
    candidate = (base / raw).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError as exc:
        raise ValidationError(f"Import reference escapes its config directory: {reference}") from exc
    if not candidate.is_file():
        raise ValidationError(f"Referenced import file not found: {reference}")
    return candidate


def _provider(provider: Any) -> tuple[str, dict[str, Any], list[str]]:
    warnings: list[str] = []
    config: dict[str, Any] = {}
    raw = provider
    if isinstance(provider, dict):
        raw = provider.get("id")
        source_config = provider.get("config") or {}
        if isinstance(source_config, dict):
            safe = {
                "temperature", "top_p", "max_tokens", "max_output_tokens",
                "seed", "frequency_penalty", "presence_penalty", "stop",
            }
            config = {key: value for key, value in source_config.items() if key in safe}
            omitted = sorted(set(source_config) - safe)
            if omitted:
                warnings.append(
                    "provider config fields were not copied (may be secret or unsupported): "
                    + ", ".join(omitted)
                )
    if not isinstance(raw, str) or not raw.strip() or raw.startswith("file://"):
        warnings.append("provider could not be translated; using echo/echo")
        return "echo/echo", config, warnings
    parts = [part for part in raw.split(":") if part]
    vendor = parts[0]
    model = parts[-1] if len(parts) > 1 else parts[0]
    vendor = {"vertex": "google", "google": "google"}.get(vendor, vendor)
    if len(parts) == 1:
        warnings.append(f"provider {raw!r} has no model component; preserved as {vendor}/{model}")
    return f"{vendor}/{model}", config, warnings


_ASSERTIONS: dict[str, tuple[str, dict[str, Any]]] = {
    "contains": ("contains", {}),
    "icontains": ("contains", {"ignore_case": True}),
    "not-contains": ("not_contains", {}),
    "not_contains": ("not_contains", {}),
    "not-icontains": ("not_contains", {"ignore_case": True}),
    "equals": ("equals", {}),
    "regex": ("regex", {}),
    "is-json": ("json_valid", {}),
    "json-valid": ("json_valid", {}),
    "llm-rubric": ("llm_judge", {}),
}


def _assertion(value: Any) -> tuple[dict[str, Any] | None, str | None]:
    if isinstance(value, str):
        value = {"type": value}
    if not isinstance(value, dict):
        return None, "non-object assertion"
    source_type = str(value.get("type") or "")
    translated = _ASSERTIONS.get(source_type)
    if translated is None:
        return None, source_type or "missing assertion type"
    target_type, additions = translated
    result: dict[str, Any] = {"type": target_type, **additions}
    for key in ("value", "threshold", "weight"):
        if key in value:
            result[key] = value[key]
    return result, None


def _matches_prompt(test: dict[str, Any], *, source_id: str, label: str) -> bool:
    selectors = test.get("prompts")
    if not selectors:
        return True
    if isinstance(selectors, str):
        selectors = [selectors]
    for selector in selectors if isinstance(selectors, list) else []:
        pattern = str(selector)
        if pattern in {source_id, label}:
            return True
        if fnmatch.fnmatchcase(source_id, pattern) or fnmatch.fnmatchcase(label, pattern):
            return True
        if source_id.startswith(pattern + ":") or label.startswith(pattern + ":"):
            return True
    return False


def _load_reference(source: ImportSource, reference: str) -> str:
    path = _safe_file(source.path.parent, reference)
    if path.suffix.lower() in {".js", ".cjs", ".mjs", ".ts", ".py"}:
        raise ValidationError(f"Executable prompt generators are not run during import: {reference}")
    return path.read_text(encoding="utf-8")


def _prompt_entries(source: ImportSource, prompts: Any) -> list[tuple[str, str, str]]:
    if isinstance(prompts, str):
        prompts = [prompts]
    if isinstance(prompts, dict) and not ("raw" in prompts or "id" in prompts):
        prompts = [{"raw": raw, "label": label} for raw, label in prompts.items()]
    if not isinstance(prompts, list):
        raise ValidationError("Promptfoo 'prompts' must be a string, mapping, or list")
    entries: list[tuple[str, str, str]] = []
    for index, item in enumerate(prompts, 1):
        label = ""
        source_id = ""
        raw: Any = item
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("display") or "")
            source_id = str(item.get("id") or "")
            raw = item.get("raw")
            if raw is None:
                raw = source_id
        if isinstance(raw, str) and raw.startswith("file://"):
            text = _load_reference(source, raw)
            source_id = source_id or raw
            label = label or Path(raw.removeprefix("file://")).stem
            chunks = re.split(r"\n---\s*\n", text)
            for chunk_index, chunk in enumerate(chunks, 1):
                chunk_label = label if len(chunks) == 1 else f"{label} {chunk_index}"
                entries.append((source_id, chunk_label, chunk.strip()))
        elif isinstance(raw, str):
            source_id = source_id or f"inline-{index}"
            label = label or source_id
            entries.append((source_id, label, raw))
        else:
            raise ValidationError(f"Promptfoo prompt {index} has no importable text")
    return entries


class PromptfooImporter:
    """Translate Promptfoo YAML/JSON configs into self-testing PromptFiles."""

    id = "promptfoo"
    contract_version = CONTRACT_VERSION

    def detect(self, data: Any) -> bool:
        document, _, _ = _unwrap(data)
        if not isinstance(document, dict) or "prompts" not in document:
            return False
        schema = str(document.get("$schema") or "")
        return "promptfoo" in schema or "providers" in document or "targets" in document

    def to_promptfiles(self, data: Any) -> list[PromptFile]:
        document, path, prefix = _unwrap(data)
        if not isinstance(document, dict) or not self.detect(data):
            raise ValidationError("Input is not a Promptfoo configuration")
        if path is None:
            path = Path("promptfooconfig.yaml").resolve()
        source = data if isinstance(data, ImportSource) else ImportSource(path, "", document, prefix)

        providers = document.get("providers", document.get("targets", []))
        if not isinstance(providers, list):
            providers = [providers]
        model_refs: list[str] = []
        provider_params: dict[str, Any] = {}
        global_warnings: list[str] = []
        for entry in providers:
            model_ref, params, warnings = _provider(entry)
            if model_ref not in model_refs:
                model_refs.append(model_ref)
            global_warnings.extend(warnings)
            if params and not provider_params:
                provider_params = params
        if not model_refs:
            model_refs = ["echo/echo"]
            global_warnings.append("no provider was declared; using echo/echo")
        if len(model_refs) > 1:
            global_warnings.append(
                "Promptfoo's provider×prompt matrix became one primary model plus fallbacks; "
                "imported evals do not prove cross-provider equivalence"
            )

        tests = document.get("tests") or []
        if isinstance(tests, str):
            if tests.startswith("file://"):
                referenced = _safe_file(source.path.parent, tests)
                if referenced.suffix.lower() not in {".yaml", ".yml", ".json"}:
                    raise ValidationError("Only YAML and JSON external test sets are imported safely")
                tests = yaml.safe_load(referenced.read_text(encoding="utf-8")) or []
            else:
                raise ValidationError("Remote or generator-backed test sets are not executed during import")
        if not isinstance(tests, list):
            raise ValidationError("Promptfoo 'tests' must resolve to a list")
        default_test = document.get("defaultTest") or {}
        if not isinstance(default_test, dict):
            default_test = {}

        used_ids: set[str] = set()
        artifacts: list[PromptFile] = []
        for index, (source_id, label, raw) in enumerate(_prompt_entries(source, document["prompts"]), 1):
            base_id = _slug(label or source_id, f"prompt-{index}")
            artifact_id = f"{_slug(prefix, 'imported')}/{base_id}"
            suffix = 2
            while artifact_id in used_ids:
                artifact_id = f"{_slug(prefix, 'imported')}/{base_id}-{suffix}"
                suffix += 1
            used_ids.add(artifact_id)

            evals: list[dict[str, Any]] = []
            warnings = list(global_warnings)
            for test_index, original in enumerate(tests, 1):
                if not isinstance(original, dict):
                    warnings.append(f"test {test_index} was not an object and was not translated")
                    continue
                test = dict(default_test)
                test.update(original)
                if not _matches_prompt(test, source_id=source_id, label=label):
                    continue
                variables = test.get("vars") or {}
                if not isinstance(variables, dict):
                    warnings.append(f"test {test_index} uses external/generated vars and is not executable in Assay")
                    variables = {}
                source_assertions = test.get("assert", default_test.get("assert", [])) or []
                if not isinstance(source_assertions, list):
                    source_assertions = [source_assertions]
                translated: list[dict[str, Any]] = []
                unsupported: list[Any] = []
                for source_assertion in source_assertions:
                    target, reason = _assertion(source_assertion)
                    if target is None:
                        unsupported.append(source_assertion)
                        warnings.append(
                            f"test {test_index} assertion {reason!r} was preserved but not translated"
                        )
                    else:
                        translated.append(target)
                eval_case: dict[str, Any] = {
                    "id": _slug(test.get("description"), f"case-{test_index}"),
                    "input": variables,
                    "assert": translated,
                }
                if test.get("description"):
                    eval_case["description"] = str(test["description"])
                if unsupported:
                    eval_case["x-promptfoo-assertions"] = unsupported
                evals.append(eval_case)

            variable_names = sorted({key for case in evals for key in case.get("input", {})})
            data_out: dict[str, Any] = {
                "promptfile": 1,
                "id": artifact_id,
                "name": label or base_id.replace("-", " ").title(),
                "summary": str(document.get("description") or f"Imported from {source.path.name}")[:160],
                "description": str(document.get("description") or "Imported Promptfoo prompt."),
                "version": 1,
                "kind": "prompt",
                "status": "draft",
                "tags": ["imported", "promptfoo"],
                "engine": {"template": "jinja2", "strict": True},
                "input": {
                    "schema": {
                        "type": "object",
                        "properties": {name: {} for name in variable_names},
                    }
                },
                "model": {
                    "primary": model_refs[0],
                    "fallbacks": model_refs[1:],
                    "params": provider_params,
                },
                "evals": evals,
                "x-import": {
                    "format": "promptfoo",
                    "source": source.path.name,
                    "source_prompt_id": source_id,
                    "warnings": list(dict.fromkeys(warnings)),
                    "untranslated_top_level_fields": sorted(
                        set(document) - {"$schema", "description", "tags", "providers", "targets", "prompts", "tests", "defaultTest"}
                    ),
                },
            }
            artifacts.append(PromptFile(data=data_out, body=raw))
        return artifacts


def _is_message(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("role"), str)
        and "content" in value
    )


def _content(value: Any, warnings: list[str]) -> Any:
    if isinstance(value, str) or value is None:
        return value or ""
    if not isinstance(value, list):
        warnings.append("a non-string message content value was converted to text")
        return json.dumps(value, ensure_ascii=False, default=str)
    parts: list[dict[str, Any]] = []
    for part in value:
        if not isinstance(part, dict):
            warnings.append("a non-object content part was converted to text")
            parts.append({"type": "text", "text": str(part)})
            continue
        kind = str(part.get("type") or "")
        if kind in {"text", "input_text", "output_text"}:
            text = part.get("text", "")
            if isinstance(text, dict):  # legacy Assistants message export
                text = text.get("value", "")
            parts.append({"type": "text", "text": str(text)})
        elif kind in {"image", "input_image", "image_url", "image_file"}:
            ref = part.get("image_url") or part.get("file_id") or part.get("ref")
            if isinstance(ref, dict):
                ref = ref.get("url") or ref.get("file_id")
            image = {"type": "image", "ref": str(ref or "")}
            if part.get("detail"):
                image["detail"] = part["detail"]
            parts.append(image)
        else:
            # PromptFile content parts are an open vocabulary. Preserve provider-specific
            # tool/refusal/document blocks instead of pretending they became plain text.
            parts.append(dict(part))
            warnings.append(f"content part type {kind or '<missing>'!r} was preserved provider-specifically")
    return parts


class MessagesImporter:
    """Import OpenAI/Anthropic-style request message arrays without executing them."""

    id = "messages"
    contract_version = CONTRACT_VERSION

    def detect(self, data: Any) -> bool:
        document, _, _ = _unwrap(data)
        if isinstance(document, list):
            return bool(document) and all(_is_message(item) for item in document)
        if not isinstance(document, dict):
            return False
        messages = document.get("messages")
        if messages is None and isinstance(document.get("input"), list):
            messages = document["input"]
        return isinstance(messages, list) and bool(messages) and all(
            _is_message(item) for item in messages
        )

    def to_promptfiles(self, data: Any) -> list[PromptFile]:
        document, path, prefix = _unwrap(data)
        if not self.detect(data):
            raise ValidationError("Input is not an OpenAI/Anthropic-style message request")
        path = path or Path("messages.json").resolve()
        wrapper = document if isinstance(document, dict) else {}
        source_messages = (
            document if isinstance(document, list)
            else wrapper.get("messages", wrapper.get("input"))
        )
        warnings = ["raw message requests carry no eval cases; the imported prompt is unverified"]
        messages: list[dict[str, Any]] = []

        instructions = wrapper.get("instructions")
        system = wrapper.get("system")
        if instructions:
            messages.append({"role": "developer", "content": _content(instructions, warnings)})
        if system:
            messages.append({"role": "system", "content": _content(system, warnings)})
        for item in source_messages:
            role = str(item["role"])
            message: dict[str, Any] = {
                "role": role,
                "content": _content(item.get("content"), warnings),
            }
            if item.get("name"):
                message["name"] = str(item["name"])
            preserved = sorted(set(item) - {"role", "content", "name"})
            if preserved:
                message["x-provider-fields"] = preserved
                warnings.append(
                    f"{role} message provider fields were not made executable: "
                    + ", ".join(preserved)
                )
            messages.append(message)

        raw_model = wrapper.get("model")
        if isinstance(raw_model, str) and raw_model.strip():
            provider, model = parse_model_ref(raw_model)
            model_ref = f"{provider}/{model}"
        else:
            model_ref = "echo/echo"
            warnings.append("no model was declared; using echo/echo until a binding is selected")
        params = {
            key: wrapper[key]
            for key in ("temperature", "top_p", "max_tokens", "max_output_tokens", "seed")
            if key in wrapper
        }
        stem = _slug(path.stem, "messages")
        recognized = {
            "model", "messages", "input", "instructions", "system",
            "temperature", "top_p", "max_tokens", "max_output_tokens", "seed",
        }
        return [PromptFile(data={
            "promptfile": 1,
            "id": f"{_slug(prefix, 'imported')}/{stem}",
            "name": stem.replace("-", " ").title(),
            "summary": f"Imported message request from {path.name}",
            "description": "Imported OpenAI/Anthropic-style message request.",
            "version": 1,
            "kind": "prompt",
            "status": "draft",
            "tags": ["imported", "messages"],
            "engine": {"template": "jinja2", "strict": True},
            "model": {"primary": model_ref, "params": params},
            "messages": messages,
            "evals": [],
            "x-import": {
                "format": "messages",
                "source": path.name,
                "warnings": list(dict.fromkeys(warnings)),
                "untranslated_top_level_fields": sorted(set(wrapper) - recognized),
            },
        })]


_DOTPROMPT = re.compile(r"^---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n(.*))?$", re.DOTALL)


def _picoschema_value(value: Any, warnings: list[str]) -> dict[str, Any]:
    if isinstance(value, dict):
        return _picoschema(value, warnings)
    if isinstance(value, list):
        return {"type": "string", "enum": value}
    raw = str(value or "any")
    declaration, _, description = raw.partition(",")
    declaration = declaration.strip()
    result: dict[str, Any]
    if declaration in {"string", "integer", "number", "boolean"}:
        result = {"type": declaration}
    elif declaration == "any":
        result = {}
    else:
        warnings.append(f"Picoschema type {declaration!r} could not be translated exactly")
        result = {}
    if description.strip():
        result["description"] = description.strip()
    return result


def _picoschema(value: Any, warnings: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        warnings.append("code-defined schema references cannot be resolved during file import")
        return {}
    if value.get("type") in {"object", "array", "string", "integer", "number", "boolean"}:
        return dict(value)
    properties: dict[str, Any] = {}
    required: list[str] = []
    additional: Any = False
    for raw_name, raw_value in value.items():
        name_spec = str(raw_name)
        if name_spec == "(*)":
            additional = _picoschema_value(raw_value, warnings)
            continue
        head = name_spec.split("(", 1)[0]
        optional = head.endswith("?")
        name = head.rstrip("?")
        options = (
            name_spec[name_spec.find("(") + 1:name_spec.rfind(")")]
            if "(" in name_spec else ""
        )
        option_parts = [part.strip() for part in options.split(",") if part.strip()]
        if "array" in option_parts:
            schema = {"type": "array", "items": _picoschema_value(raw_value, warnings)}
        elif "enum" in option_parts:
            values = raw_value if isinstance(raw_value, list) else [raw_value]
            schema = {"type": "string", "enum": values}
        elif "object" in option_parts or isinstance(raw_value, dict):
            schema = _picoschema(raw_value, warnings)
        else:
            schema = _picoschema_value(raw_value, warnings)
        descriptions = [part for part in option_parts if part not in {"array", "enum", "object"}]
        if descriptions:
            schema.setdefault("description", ", ".join(descriptions))
        if optional:
            schema = {"anyOf": [schema, {"type": "null"}]}
        else:
            required.append(name)
        properties[name] = schema
    result: dict[str, Any] = {
        "type": "object", "properties": properties, "additionalProperties": additional,
    }
    if required:
        result["required"] = required
    return result


class DotpromptImporter:
    """Import Genkit ``.prompt`` files, preserving unsupported Handlebars literally."""

    id = "dotprompt"
    contract_version = CONTRACT_VERSION

    def detect(self, data: Any) -> bool:
        document, path, _ = _unwrap(data)
        return isinstance(document, str) and (
            (path is not None and path.suffix.lower() == ".prompt")
            or bool(_DOTPROMPT.match(document.lstrip("\ufeff")))
        )

    def to_promptfiles(self, data: Any) -> list[PromptFile]:
        document, path, prefix = _unwrap(data)
        if not self.detect(data):
            raise ValidationError("Input is not a Genkit dotprompt file")
        path = path or Path("prompt.prompt").resolve()
        text = str(document).lstrip("\ufeff")
        match = _DOTPROMPT.match(text)
        if match:
            try:
                frontmatter = yaml.safe_load(match.group(1)) or {}
            except yaml.YAMLError as exc:
                raise ValidationError(f"Invalid dotprompt frontmatter: {exc}") from exc
            body = (match.group(2) or "").strip("\r\n")
        else:
            frontmatter, body = {}, text.strip("\r\n")
        if not isinstance(frontmatter, dict):
            raise ValidationError("Dotprompt frontmatter must be a mapping")

        warnings = ["dotprompt files carry no embedded eval evidence; the import is unverified"]
        raw_model = frontmatter.get("model")
        if isinstance(raw_model, str) and raw_model:
            vendor, _, model = raw_model.partition("/")
            vendor = {"googleai": "google", "vertexai": "google"}.get(vendor, vendor)
            model_ref = f"{vendor}/{model}" if model else parse_model_ref(raw_model)[0] + "/" + raw_model
        else:
            model_ref = "echo/echo"
            warnings.append("no model was declared; using echo/echo until a binding is selected")

        config = frontmatter.get("config") or {}
        params: dict[str, Any] = {}
        if isinstance(config, dict):
            parameter_names = {
                "temperature": "temperature", "topK": "top_k", "topP": "top_p",
                "maxOutputTokens": "max_tokens", "stopSequences": "stop", "seed": "seed",
            }
            params = {target: config[source] for source, target in parameter_names.items() if source in config}
            omitted = sorted(set(config) - set(parameter_names))
            if omitted:
                warnings.append("dotprompt config fields were not translated: " + ", ".join(omitted))

        simple_tokens = re.findall(r"{{(.*?)}}", body, re.DOTALL)
        simple_template = all(
            re.fullmatch(r"\s*[A-Za-z_][A-Za-z0-9_.]*\s*", token) for token in simple_tokens
        )
        if not simple_template:
            warnings.append(
                "Handlebars helpers/partials were preserved literally; renderer is 'none' until "
                "a compatible renderer is installed or the template is rewritten"
            )

        input_block = frontmatter.get("input") or {}
        output_block = frontmatter.get("output") or {}
        input_schema = _picoschema(input_block.get("schema"), warnings) if isinstance(input_block, dict) and input_block.get("schema") else None
        output_schema = _picoschema(output_block.get("schema"), warnings) if isinstance(output_block, dict) and output_block.get("schema") else None
        stem = _slug(path.stem, "prompt")
        data_out: dict[str, Any] = {
            "promptfile": 1,
            "id": f"{_slug(prefix, 'imported')}/{stem}",
            "name": str(frontmatter.get("name") or stem.replace("-", " ").title()),
            "summary": str(frontmatter.get("description") or f"Imported dotprompt from {path.name}")[:160],
            "description": str(frontmatter.get("description") or "Imported Genkit dotprompt."),
            "version": 1,
            "kind": "prompt",
            "status": "draft",
            "tags": ["imported", "dotprompt"],
            "engine": {"template": "jinja2" if simple_template else "none", "strict": True},
            "model": {"primary": model_ref, "params": params},
            "evals": [],
            "x-import": {
                "format": "dotprompt",
                "source": path.name,
                "template_executable": simple_template,
                "warnings": list(dict.fromkeys(warnings)),
                "untranslated_frontmatter_fields": sorted(
                    set(frontmatter) - {"name", "description", "model", "config", "input", "output"}
                ),
            },
        }
        if not simple_template:
            data_out["requires"] = {"capabilities": ["dotprompt-runtime"]}
        if input_schema:
            data_out["input"] = {"schema": input_schema}
            if isinstance(input_block, dict) and "default" in input_block:
                data_out["input"]["default"] = input_block["default"]
        if output_schema:
            data_out["output"] = {"schema": output_schema}
        return [PromptFile(data=data_out, body=body)]


def _xml_tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1].lower()


def _poml_model(raw_model: str | None) -> str:
    if not raw_model:
        return "echo/echo"
    provider, model = parse_model_ref(raw_model)
    return f"{provider}/{model}"


def _poml_block(element: ET.Element) -> str:
    tag = _xml_tag(element)
    text = "".join(element.itertext()).strip()
    caption = element.attrib.get("caption")
    if tag == "role":
        return f"# {caption or 'Role'}\n\n{text}"
    if tag == "task":
        return f"# {caption or 'Task'}\n\n{text}"
    return text


class PomlImporter:
    """Import the static, text-safe subset of Microsoft POML.

    POML supports JavaScript expressions, file inclusion, loops, conditions, stylesheets,
    data components and custom components. Those require the POML runtime; this importer
    preserves such documents verbatim with the passthrough renderer instead of approximating
    their output and claiming equivalence.
    """

    id = "poml"
    contract_version = CONTRACT_VERSION

    _META: ClassVar[set[str]] = {"meta", "runtime", "output-schema"}
    _STATIC: ClassVar[set[str]] = {
        "poml",
        "role",
        "task",
        "p",
        "text",
        "system-msg",
        "user-msg",
        "assistant-msg",
    }
    _MESSAGE_ROLES: ClassVar[dict[str, str]] = {
        "system-msg": "system", "user-msg": "user", "assistant-msg": "assistant",
        "system": "system", "human": "user", "user": "user", "ai": "assistant",
        "assistant": "assistant",
    }

    def detect(self, data: Any) -> bool:
        document, path, _ = _unwrap(data)
        return isinstance(document, str) and (
            (path is not None and path.suffix.lower() == ".poml")
            or document.lstrip().lower().startswith("<poml")
        )

    def to_promptfiles(self, data: Any) -> list[PromptFile]:
        document, path, prefix = _unwrap(data)
        if not self.detect(data):
            raise ValidationError("Input is not a POML document")
        path = path or Path("prompt.poml").resolve()
        source = str(document)
        lowered = source.lower()
        if "<!doctype" in lowered or "<!entity" in lowered:
            raise ValidationError("POML imports may not contain DTD or entity declarations")
        try:
            root = ET.fromstring(source)
        except ET.ParseError as exc:
            raise ValidationError(f"Invalid POML XML: {exc}") from exc
        if _xml_tag(root) != "poml":
            raise ValidationError("POML standalone files must have a <poml> root")

        warnings = ["POML files carry no embedded eval evidence; the import is unverified"]
        tags = {_xml_tag(element) for element in root.iter()}
        unsupported = sorted(tags - self._STATIC - self._META)
        dynamic = []
        for element in root.iter():
            tag = _xml_tag(element)
            attrs = {key.lower() for key in element.attrib}
            allowed_attrs: set[str] = set()
            if tag in {"role", "task"}:
                allowed_attrs.add("caption")
            if tag in self._MESSAGE_ROLES:
                allowed_attrs.add("speaker")
            if tag == "runtime":
                allowed_attrs |= {
                    "model",
                    "temperature",
                    "top-p",
                    "max-output-tokens",
                    "seed",
                }
            if tag == "output-schema":
                allowed_attrs.add("parser")
            if (
                attrs - allowed_attrs
                or tag in {"let", "include", "stylesheet", "tool-definition", "tool"}
            ):
                dynamic.append(tag)
        tokens = re.findall(r"{{(.*?)}}", source, re.DOTALL)
        complex_expressions = [
            token for token in tokens
            if not re.fullmatch(r"\s*[A-Za-z_][A-Za-z0-9_.]*\s*", token)
        ]
        executable = not unsupported and not dynamic and not complex_expressions
        if unsupported:
            warnings.append("unsupported POML components require its runtime: " + ", ".join(unsupported))
        if dynamic:
            warnings.append("POML conditions, loops, includes, or data sources require its runtime")
        if complex_expressions:
            warnings.append("POML JavaScript expressions were preserved but not evaluated")

        runtime = next(
            (element for element in root.iter() if _xml_tag(element) == "runtime"), None
        )
        runtime_attrs = dict(runtime.attrib) if runtime is not None else {}
        model_ref = _poml_model(runtime_attrs.get("model"))
        if model_ref == "echo/echo":
            warnings.append("no runtime model was declared; using echo/echo until a binding is selected")
        runtime_params = {
            "temperature": "temperature", "top-p": "top_p",
            "max-output-tokens": "max_tokens", "seed": "seed",
        }
        params: dict[str, Any] = {}
        for source_key, target_key in runtime_params.items():
            if source_key not in runtime_attrs:
                continue
            raw = runtime_attrs[source_key]
            try:
                params[target_key] = int(raw) if target_key in {"max_tokens", "seed"} else float(raw)
            except ValueError:
                warnings.append(f"runtime parameter {source_key!r} was not numeric and was omitted")

        output_schema = None
        schema_element = next(
            (element for element in root.iter() if _xml_tag(element) == "output-schema"),
            None,
        )
        if schema_element is not None:
            if schema_element.attrib.get("parser", "json") == "json" and not re.search(
                r"{{.*?}}", schema_element.text or "", re.DOTALL
            ):
                try:
                    output_schema = json.loads(schema_element.text or "{}")
                except json.JSONDecodeError:
                    warnings.append("JSON output schema was invalid and was not translated")
                    executable = False
            else:
                warnings.append("expression-backed output schemas require the POML runtime")
                executable = False

        messages: list[dict[str, Any]] = []
        blocks: list[str] = []

        def flush_blocks() -> None:
            content = "\n\n".join(block for block in blocks if block).strip()
            if content:
                messages.append({"role": "user", "content": content})
            blocks.clear()

        if executable:
            for element in root:
                tag = _xml_tag(element)
                if tag in self._META:
                    continue
                speaker = element.attrib.get("speaker", "").lower()
                role = self._MESSAGE_ROLES.get(tag) or self._MESSAGE_ROLES.get(speaker)
                if role:
                    flush_blocks()
                    messages.append({"role": role, "content": _poml_block(element)})
                else:
                    blocks.append(_poml_block(element))
            flush_blocks()
        else:
            warnings.append(
                "the original POML is preserved with renderer 'none'; it is not claimed as "
                "equivalent model input until a POML renderer is installed"
            )

        variables = sorted(
            {
                token.strip().split(".", 1)[0]
                for token in tokens
                if re.fullmatch(r"\s*[A-Za-z_][A-Za-z0-9_.]*\s*", token)
            }
        )
        stem = _slug(path.stem, "prompt")
        data_out: dict[str, Any] = {
            "promptfile": 1,
            "id": f"{_slug(prefix, 'imported')}/{stem}",
            "name": stem.replace("-", " ").title(),
            "summary": f"Imported POML prompt from {path.name}",
            "description": "Imported Microsoft Prompt Orchestration Markup Language document.",
            "version": 1,
            "kind": "prompt",
            "status": "draft",
            "tags": ["imported", "poml"],
            "engine": {"template": "jinja2" if executable else "none", "strict": True},
            "input": {"schema": {
                "type": "object", "properties": {name: {} for name in variables},
            }},
            "model": {"primary": model_ref, "params": params},
            "evals": [],
            "x-import": {
                "format": "poml", "source": path.name,
                "template_executable": executable,
                "warnings": list(dict.fromkeys(warnings)),
            },
            "x-poml": {"source": source},
        }
        if executable and messages:
            data_out["messages"] = messages
        if not executable:
            data_out["requires"] = {"capabilities": ["poml-runtime"]}
        if output_schema:
            data_out["output"] = {"schema": output_schema}
        return [PromptFile(data=data_out, body="" if executable else source)]


_SAFE_MODEL_PARAMS = {
    "temperature": "temperature",
    "top_p": "top_p",
    "max_tokens": "max_tokens",
    "max_completion_tokens": "max_tokens",
    "max_output_tokens": "max_tokens",
    "seed": "seed",
    "frequency_penalty": "frequency_penalty",
    "presence_penalty": "presence_penalty",
    "stop": "stop",
}


def _registry_model(provider: Any, model: Any, warnings: list[str]) -> str:
    raw_model = str(model or "").strip()
    raw_provider = str(provider or "").strip()
    if not raw_model:
        warnings.append("no registry model was declared; using echo/echo until one is selected")
        return "echo/echo"
    if "/" in raw_model:
        return raw_model
    if raw_provider:
        normalized = {"googleai": "google", "vertexai": "google"}.get(
            raw_provider, raw_provider
        )
        return f"{normalized}/{raw_model}"
    inferred_provider, inferred_model = parse_model_ref(raw_model)
    return f"{inferred_provider}/{inferred_model}"


def _registry_params(config: Any, warnings: list[str]) -> tuple[dict[str, Any], set[str]]:
    if not isinstance(config, dict):
        if config not in (None, {}):
            warnings.append("non-object model configuration was not translated")
        return {}, set()
    params = {
        target: config[source]
        for source, target in _SAFE_MODEL_PARAMS.items()
        if source in config
    }
    return params, set(config) - set(_SAFE_MODEL_PARAMS)


def _simple_jinja_variables(values: list[str]) -> tuple[list[str], bool]:
    tokens = [token for value in values for token in re.findall(r"{{(.*?)}}", value, re.DOTALL)]
    simple = all(
        re.fullmatch(r"\s*[A-Za-z_][A-Za-z0-9_.]*\s*", token) for token in tokens
    )
    roots = sorted(
        {
            token.strip().split(".", 1)[0]
            for token in tokens
            if re.fullmatch(r"\s*[A-Za-z_][A-Za-z0-9_.]*\s*", token)
        }
    )
    return roots, simple


def _fstring_variables(values: list[str]) -> tuple[list[str], bool]:
    roots: set[str] = set()
    try:
        for value in values:
            for _, field_name, _, _ in string.Formatter().parse(value):
                if field_name:
                    roots.add(field_name.split(".", 1)[0].split("[", 1)[0])
    except ValueError:
        return [], False
    return sorted(roots), True


def _input_schema(variables: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": {name: {} for name in variables}}


def _safe_version(value: Any, warnings: list[str]) -> int:
    try:
        version = int(value or 1)
    except (TypeError, ValueError):
        warnings.append("registry version was invalid; PromptFile version defaults to 1")
        return 1
    if version < 1:
        warnings.append("registry version was below 1; PromptFile version defaults to 1")
        return 1
    return version


class LangfuseImporter:
    """Import one response from Langfuse's provider-agnostic prompt API."""

    id = "langfuse"
    contract_version = CONTRACT_VERSION

    def detect(self, data: Any) -> bool:
        document, _, _ = _unwrap(data)
        return (
            isinstance(document, dict)
            and document.get("type") in {"text", "chat"}
            and "name" in document
            and "prompt" in document
        )

    def to_promptfiles(self, data: Any) -> list[PromptFile]:
        document, path, prefix = _unwrap(data)
        if not self.detect(data):
            raise ValidationError("Input is not a Langfuse prompt response")
        path = path or Path("langfuse-prompt.json").resolve()
        warnings = ["Langfuse prompt responses carry no embedded eval evidence; import is unverified"]
        prompt_type = document["type"]
        raw_prompt = document["prompt"]
        messages: list[dict[str, Any]] = []
        template_values: list[str] = []
        executable = True

        if prompt_type == "text" and isinstance(raw_prompt, str):
            body = raw_prompt
            template_values.append(raw_prompt)
        elif prompt_type == "chat" and isinstance(raw_prompt, list):
            body = ""
            for raw_message in raw_prompt:
                if not isinstance(raw_message, dict):
                    executable = False
                    continue
                if not isinstance(raw_message.get("content"), str):
                    executable = False
                    messages.append(
                        {
                            "role": str(raw_message.get("role") or "user"),
                            "content": raw_message.get("content"),
                        }
                    )
                    continue
                message = {
                    "role": str(raw_message.get("role") or "user"),
                    "content": raw_message["content"],
                }
                if raw_message.get("name"):
                    message["name"] = str(raw_message["name"])
                unknown_message_fields = sorted(
                    set(raw_message) - {"role", "content", "name"}
                )
                if unknown_message_fields:
                    executable = False
                    warnings.append(
                        "Langfuse message fields require its runtime: "
                        + ", ".join(unknown_message_fields)
                    )
                messages.append(message)
                template_values.append(raw_message["content"])
            if len(messages) != len(raw_prompt):
                warnings.append("non-text Langfuse chat messages require its runtime")
        else:
            raise ValidationError("Langfuse prompt type does not match its prompt payload")

        variables, simple_template = _simple_jinja_variables(template_values)
        if not simple_template:
            executable = False
            warnings.append("complex Langfuse template expressions require its runtime")
        if any("@@@langfusePrompt:" in value for value in template_values):
            executable = False
            warnings.append("Langfuse prompt references require its runtime")

        config = document.get("config") or {}
        params, unknown_config = _registry_params(config, warnings)
        model_ref = _registry_model(None, config.get("model") if isinstance(config, dict) else None, warnings)
        output_schema = None
        allowed_config = set(_SAFE_MODEL_PARAMS) | {"model", "response_format"}
        unknown_config -= {"model", "response_format"}
        response_format = config.get("response_format") if isinstance(config, dict) else None
        if isinstance(response_format, dict) and response_format.get("type") == "json_schema":
            schema_wrapper = response_format.get("json_schema") or {}
            if isinstance(schema_wrapper, dict) and isinstance(schema_wrapper.get("schema"), dict):
                output_schema = schema_wrapper["schema"]
            else:
                executable = False
                warnings.append("Langfuse JSON response schema was not in a translatable shape")
        elif response_format is not None:
            executable = False
            warnings.append("Langfuse response_format requires its runtime")
        if unknown_config:
            executable = False
            warnings.append(
                "Langfuse config fields require application-specific handling: "
                + ", ".join(sorted(unknown_config))
            )

        name = str(document["name"])
        source_meta = data.metadata if isinstance(data, ImportSource) else {}
        request_meta = dict(source_meta.get("registry_request") or {})
        labels = [str(item) for item in document.get("labels") or []]
        source_tags = [str(item) for item in document.get("tags") or []]
        data_out: dict[str, Any] = {
            "promptfile": 1,
            "id": f"{_slug(prefix, 'imported')}/{_slug(name)}",
            "name": name,
            "summary": f"Imported Langfuse prompt {name}"[:160],
            "description": "Imported from the Langfuse provider-agnostic prompt API.",
            "version": _safe_version(document.get("version"), warnings),
            "kind": "prompt",
            "status": "draft",
            "tags": list(dict.fromkeys(["imported", "langfuse", *source_tags, *labels])),
            "engine": {"template": "jinja2" if executable else "none", "strict": True},
            "input": {"schema": _input_schema(variables)},
            "model": {"primary": model_ref, "params": params},
            "evals": [],
            "x-import": {
                "format": "langfuse",
                "source": source_meta.get("source_uri", path.name),
                "template_executable": executable,
                "warnings": list(dict.fromkeys(warnings)),
            },
            "x-langfuse": {
                "name": name,
                "version": document.get("version"),
                "labels": labels,
                "tags": source_tags,
                "request": request_meta,
                "untranslated_config_fields": sorted(set(config) - allowed_config)
                if isinstance(config, dict)
                else [],
            },
        }
        if not executable:
            data_out["x-langfuse"]["untranslated_prompt"] = raw_prompt
        if messages:
            data_out["messages"] = messages
        if not executable:
            data_out["requires"] = {"capabilities": ["langfuse-runtime"]}
        if output_schema:
            data_out["output"] = {"schema": output_schema}
        return [PromptFile(data=data_out, body=body)]


def _promptlayer_text(value: Any) -> tuple[Any, bool]:
    if isinstance(value, str):
        return value, True
    if not isinstance(value, list):
        return value, False
    texts: list[str] = []
    executable = True
    for part in value:
        if not isinstance(part, dict) or part.get("type") != "text" or not isinstance(
            part.get("text"), str
        ):
            return value, False
        texts.append(part["text"])
        if set(part) - {"type", "text", "id"}:
            executable = False
    return "".join(texts), executable


class PromptLayerImporter:
    """Import PromptLayer's stable raw, provider-agnostic template response."""

    id = "promptlayer"
    contract_version = CONTRACT_VERSION

    def detect(self, data: Any) -> bool:
        document, _, _ = _unwrap(data)
        return (
            isinstance(document, dict)
            and "prompt_name" in document
            and isinstance(document.get("prompt_template"), dict)
        )

    def to_promptfiles(self, data: Any) -> list[PromptFile]:
        document, path, prefix = _unwrap(data)
        if not self.detect(data):
            raise ValidationError("Input is not a PromptLayer raw template response")
        path = path or Path("promptlayer-template.json").resolve()
        warnings = [
            "PromptLayer template responses carry no embedded eval evidence; import is unverified"
        ]
        template = document["prompt_template"]
        template_type = template.get("type")
        template_format = str(template.get("template_format") or "f-string").lower()
        executable = template_format in {"f-string", "fstring", "jinja2"}
        renderer = "jinja2" if template_format == "jinja2" else "fstring"
        if not executable:
            renderer = "none"
            warnings.append(f"PromptLayer template format {template_format!r} requires its runtime")

        messages: list[dict[str, Any]] = []
        template_values: list[str] = []
        body = ""
        if template_type == "chat" and isinstance(template.get("messages"), list):
            for raw_message in template["messages"]:
                if not isinstance(raw_message, dict):
                    executable = False
                    continue
                content, content_executable = _promptlayer_text(raw_message.get("content"))
                executable = executable and content_executable and isinstance(content, str)
                message = {"role": str(raw_message.get("role") or "user"), "content": content}
                if raw_message.get("name"):
                    message["name"] = str(raw_message["name"])
                if set(raw_message) - {"role", "content", "name"}:
                    executable = False
                messages.append(message)
                if isinstance(content, str):
                    template_values.append(content)
        elif template_type == "completion":
            content = template.get("content", template.get("template"))
            converted, content_executable = _promptlayer_text(content)
            executable = executable and content_executable and isinstance(converted, str)
            if isinstance(converted, str):
                body = converted
                template_values.append(converted)
            else:
                messages = [{"role": "user", "content": converted}]
        else:
            raise ValidationError("PromptLayer template type does not match its payload")

        if renderer == "jinja2":
            variables, syntax_ok = _simple_jinja_variables(template_values)
        else:
            variables, syntax_ok = _fstring_variables(template_values)
        if not syntax_ok:
            executable = False
            warnings.append("PromptLayer template syntax could not be translated safely")
        if any("@@@" in value for value in template_values):
            executable = False
            warnings.append("unresolved PromptLayer snippet references require its runtime")

        metadata = document.get("metadata") or {}
        model = metadata.get("model") if isinstance(metadata, dict) else {}
        model = model if isinstance(model, dict) else {}
        model_ref = _registry_model(model.get("provider"), model.get("name"), warnings)
        params, unknown_params = _registry_params(model.get("parameters") or {}, warnings)
        if unknown_params:
            executable = False
            warnings.append(
                "PromptLayer model parameters require application-specific handling: "
                + ", ".join(sorted(unknown_params))
            )
        if not executable:
            renderer = "none"
            warnings.append("the imported template is capability-gated before any provider call")

        name = str(document["prompt_name"])
        source_meta = data.metadata if isinstance(data, ImportSource) else {}
        source_tags = [str(item) for item in document.get("tags") or []]
        data_out: dict[str, Any] = {
            "promptfile": 1,
            "id": f"{_slug(prefix, 'imported')}/{_slug(name)}",
            "name": name,
            "summary": f"Imported PromptLayer template {name}"[:160],
            "description": "Imported from PromptLayer's raw provider-agnostic template API.",
            "version": _safe_version(document.get("version"), warnings),
            "kind": "prompt",
            "status": "draft",
            "tags": list(dict.fromkeys(["imported", "promptlayer", *source_tags])),
            "engine": {"template": renderer, "strict": True},
            "input": {"schema": _input_schema(variables)},
            "model": {"primary": model_ref, "params": params},
            "evals": [],
            "x-import": {
                "format": "promptlayer",
                "source": source_meta.get("source_uri", path.name),
                "template_executable": executable,
                "warnings": list(dict.fromkeys(warnings)),
            },
            "x-promptlayer": {
                "id": document.get("id"),
                "workspace_id": document.get("workspace_id"),
                "version": document.get("version"),
                "commit_message": document.get("commit_message"),
                "created_at": document.get("created_at"),
                "request": dict(source_meta.get("registry_request") or {}),
                "untranslated_model_parameter_fields": sorted(unknown_params),
            },
        }
        if not executable:
            data_out["x-promptlayer"]["untranslated_prompt_template"] = template
        if messages:
            data_out["messages"] = messages
        if not executable:
            data_out["requires"] = {"capabilities": ["promptlayer-runtime"]}
        return [PromptFile(data=data_out, body=body)]
