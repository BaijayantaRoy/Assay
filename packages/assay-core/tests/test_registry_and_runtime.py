"""Registry, runtime, guardrails and evaluation.

Everything here runs offline against the ``echo`` provider — see ADR-0005. No test in
this file requires an API key or network access.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import assay_core.registry as registry_module

from assay_core import (
    CapabilityError,
    GuardrailViolation,
    PromptFile,
    Registry,
    Runtime,
    Workspace,
)
from assay_core.builtins.evaluators import aggregate
from assay_core.builtins.stores import MemoryStore
from assay_core.catalog import ModelCatalog, parse_model_ref
from assay_core.contracts import CONTRACT_VERSION, EvalResult
from assay_core.errors import IncompatiblePlugin, PluginNotFound


@pytest.fixture
def registry():
    return Registry()


@pytest.fixture
def runtime(tmp_path):
    return Runtime(workspace=Workspace(root=tmp_path), default_model="echo/echo")


def make(source: str) -> PromptFile:
    return PromptFile.parse(source)


BASIC = """---
promptfile: 1
id: t/basic
model:
  primary: echo/echo
---
Hello {{ name }}.
"""


# -- registry --------------------------------------------------------------


def test_builtins_are_discoverable(registry):
    assert "jinja2" in registry.names("assay.renderers")
    assert {"openai", "anthropic", "google", "ollama", "echo"} <= set(
        registry.names("assay.providers")
    )
    assert "llm_judge" in registry.names("assay.evaluators")
    assert "pii" in registry.names("assay.guardrails")


def test_explicitly_scoped_registry_does_not_scan_installed_plugins(monkeypatch):
    def unexpected_scan(*, group):
        raise AssertionError(f"scoped registry scanned {group}")

    monkeypatch.setattr(registry_module, "entry_points", unexpected_scan)
    scoped = Registry(autoload=False)

    assert scoped.names("assay.providers") == []


def test_concurrent_registry_scan_never_exposes_partial_inventory(monkeypatch):
    """A second HTTP worker must not observe `_scanned` before population finishes."""
    discovery_started = threading.Event()
    release_discovery = threading.Event()
    second_worker_started = threading.Event()

    def delayed_entry_points(*, group):
        discovery_started.set()
        assert release_discovery.wait(timeout=5), f"timed out scanning {group}"
        return []

    monkeypatch.setattr(registry_module, "entry_points", delayed_entry_points)
    concurrent = Registry()

    def first_worker():
        return concurrent.names("assay.renderers")

    def second_worker():
        second_worker_started.set()
        return concurrent.names("assay.renderers")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(first_worker)
        assert discovery_started.wait(timeout=5)
        second = pool.submit(second_worker)
        assert second_worker_started.wait(timeout=5)
        release_discovery.set()
        assert "jinja2" in first.result(timeout=5)
        assert "jinja2" in second.result(timeout=5)


def test_unknown_plugin_raises_with_available_names(registry):
    with pytest.raises(PluginNotFound) as exc:
        registry.get("assay.renderers", "nope")
    assert "jinja2" in exc.value.context["available"]


def test_unknown_group_is_rejected(registry):
    with pytest.raises(PluginNotFound):
        registry.get("assay.not_a_group", "x")


def test_plugin_with_wrong_contract_major_is_refused(registry):
    class Ancient:
        id = "ancient"
        contract_version = "0.4"

        def render(self, template, variables, *, strict=True):
            return template

        def variables_of(self, template):
            return set()

    with pytest.raises(IncompatiblePlugin):
        registry.register("assay.renderers", "ancient", Ancient())


def test_plugin_missing_contract_version_is_refused(registry):
    class NoVersion:
        id = "nv"

        def render(self, template, variables, *, strict=True):
            return template

        def variables_of(self, template):
            return set()

    with pytest.raises(IncompatiblePlugin):
        registry.register("assay.renderers", "nv", NoVersion())


def test_third_party_plugin_registers_and_is_used(tmp_path):
    """The whole promise of ADR-0002, exercised end to end."""

    class Shouty:
        id = "shouty"
        contract_version = CONTRACT_VERSION

        def render(self, template, variables, *, strict=True):
            return template.upper()

        def variables_of(self, template):
            return set()

    registry = Registry()
    registry.register("assay.renderers", "shouty", Shouty())
    runtime = Runtime(workspace=Workspace(root=tmp_path), registry=registry,
                      default_model="echo/echo")
    pf = make("---\npromptfile: 1\nid: t/s\nengine: {template: shouty}\n---\nquiet text")
    assert "QUIET TEXT" in runtime.run(pf).text


def test_describe_reports_every_group(registry):
    inventory = registry.describe()
    assert set(inventory) >= {"assay.renderers", "assay.providers", "assay.evaluators",
                              "assay.guardrails", "assay.stores", "assay.importers",
                              "assay.tracers"}


# -- catalogue -------------------------------------------------------------


def test_model_ref_parsing():
    assert parse_model_ref("anthropic/claude-opus-4") == ("anthropic", "claude-opus-4")
    assert parse_model_ref("ollama/llama3.3:8b") == ("ollama", "llama3.3:8b")
    assert parse_model_ref("claude-something-new")[0] == "anthropic"
    assert parse_model_ref("gpt-9")[0] == "openai"


def test_unknown_model_prices_at_zero_rather_than_raising():
    """ADR-0005: unpriced must still be runnable."""
    assert ModelCatalog.default().get("nobody/nothing") is None


# -- rendering -------------------------------------------------------------


def test_render_substitutes_variables(runtime):
    rendered = runtime.render(make(BASIC), {"name": "Ada"})
    assert rendered.messages[0].content == "Hello Ada."


def test_strict_mode_raises_on_missing_variable(runtime):
    from assay_core.errors import RenderError

    with pytest.raises(RenderError):
        runtime.render(make(BASIC), {})


def test_non_strict_mode_tolerates_missing_variable(runtime):
    pf = make("---\npromptfile: 1\nid: t/lax\nengine: {strict: false}\n---\nHi {{ missing }}.")
    assert runtime.render(pf, {}).messages[0].content.strip() == "Hi ."


def test_jinja_sandbox_blocks_dunder_access(runtime):
    from assay_core.errors import RenderError

    pf = make("---\npromptfile: 1\nid: t/evil\n---\n{{ ''.__class__.__mro__ }}")
    with pytest.raises(RenderError):
        runtime.render(pf, {})


# -- capability gate -------------------------------------------------------


def test_unmet_capability_fails_closed(runtime):
    pf = make(
        "---\npromptfile: 1\nid: t/cap\nrequires: {capabilities: [telepathy]}\n"
        "model: {primary: echo/echo}\n---\nx"
    )
    with pytest.raises(CapabilityError) as exc:
        runtime.run(pf)
    assert "telepathy" in exc.value.context["required"]


def test_met_capability_passes(runtime):
    pf = make(
        "---\npromptfile: 1\nid: t/cap2\nrequires: {capabilities: [json_mode]}\n"
        "model: {primary: echo/echo}\n---\nx"
    )
    assert runtime.run(pf).text


def test_insufficient_context_window_fails_closed(runtime):
    pf = make(
        "---\npromptfile: 1\nid: t/ctx\nrequires: {min_context_tokens: 999999999}\n"
        "model: {primary: openai/gpt-4o-mini}\n---\nx"
    )
    with pytest.raises(CapabilityError):
        runtime.run(pf)


def test_unknown_context_window_fails_closed(runtime):
    pf = make(
        "---\npromptfile: 1\nid: t/ctx-unknown\n"
        "requires: {min_context_tokens: 1000}\n"
        "model: {primary: echo/not-in-catalog}\n---\nx"
    )
    with pytest.raises(CapabilityError) as raised:
        runtime.run(pf)
    assert raised.value.context["available_context"] is None


def test_every_configured_fallback_must_satisfy_capabilities(runtime):
    pf = make(
        "---\npromptfile: 1\nid: t/fallback-cap\n"
        "requires: {min_context_tokens: 1000}\n"
        "model:\n  primary: echo/echo\n  fallbacks: [echo/not-in-catalog]\n---\nx"
    )
    with pytest.raises(CapabilityError) as raised:
        runtime.run(pf)
    assert raised.value.context["model"] == "echo/not-in-catalog"


# -- execution -------------------------------------------------------------


def test_run_returns_usage_and_cost(runtime):
    result = runtime.run(make(BASIC), {"name": "Ada"})
    assert result.completion.provider == "echo"
    assert result.completion.usage.total_tokens > 0
    assert result.cost_usd == 0.0
    payload = result.to_dict()
    assert payload["prompt_id"] == "t/basic" and payload["run_id"]


def test_fallback_is_used_when_primary_fails(runtime):
    pf = make(
        "---\npromptfile: 1\nid: t/fb\nmodel:\n  primary: openai/gpt-4o\n"
        "  fallbacks: [echo/echo]\n---\nhi"
    )
    result = runtime.run(pf)  # no OPENAI_API_KEY -> primary raises AuthError
    assert result.fallback_used == "echo/echo"
    assert result.completion.provider == "echo"


def test_all_models_failing_raises_provider_error(runtime):
    from assay_core.errors import ProviderError

    pf = make("---\npromptfile: 1\nid: t/dead\nmodel: {primary: openai/gpt-4o}\n---\nhi")
    with pytest.raises(ProviderError):
        runtime.run(pf)


# -- guardrails ------------------------------------------------------------


def test_blocking_input_guardrail_raises(runtime):
    pf = make(
        "---\npromptfile: 1\nid: t/g1\nmodel: {primary: echo/echo}\n"
        "guardrails:\n  - {type: regex_block, stage: input, action: block,"
        " config: {pattern: 'secret'}}\n---\nthis contains a secret word"
    )
    with pytest.raises(GuardrailViolation):
        runtime.run(pf)


def test_redacting_guardrail_transforms_and_continues(runtime):
    pf = make(
        "---\npromptfile: 1\nid: t/g2\nmodel: {primary: echo/echo}\n"
        "guardrails:\n  - {type: pii, stage: input, action: redact}\n"
        "---\nContact me at ada@example.com please."
    )
    result = runtime.run(pf)
    assert "ada@example.com" not in result.text
    assert "[EMAIL]" in result.text
    assert result.guardrail_events[0]["guardrail"] == "pii"


def test_output_guardrail_warn_records_without_raising(runtime):
    pf = make(
        "---\npromptfile: 1\nid: t/g3\nmodel: {primary: echo/echo}\n"
        "guardrails:\n  - {type: max_length, stage: output, action: warn,"
        " config: {max_chars: 3}}\n---\nthis output is definitely longer than three"
    )
    result = runtime.run(pf)
    assert result.guardrail_events
    assert result.guardrail_events[0]["action"] == "warn"


def test_missing_declared_guardrail_fails_closed(runtime):
    pf = make(
        "---\npromptfile: 1\nid: t/missing-guardrail\nmodel: {primary: echo/echo}\n"
        "guardrails:\n  - {type: not_installed, stage: input, action: block}\n"
        "---\nhello"
    )
    with pytest.raises(GuardrailViolation) as raised:
        runtime.run(pf)
    assert raised.value.context["guardrail"] == "not_installed"


def test_skip_guardrails_bypasses_the_gate(runtime):
    pf = make(
        "---\npromptfile: 1\nid: t/g4\nmodel: {primary: echo/echo}\n"
        "guardrails:\n  - {type: regex_block, stage: input, action: block,"
        " config: {pattern: 'secret'}}\n---\ncontains secret"
    )
    assert runtime.run(pf, skip_guardrails=True).text


# -- evaluation ------------------------------------------------------------


EVAL_PROMPT = """---
promptfile: 1
id: t/eval
model: {primary: echo/echo}
evals:
  - id: pass-case
    input: {word: otters}
    assert:
      - {type: contains, value: otters}
      - {type: not_contains, value: badgers}
      - {type: cost_under, value: 1.0}
      - {type: latency_under, value: 60000}
  - id: fail-case
    input: {word: otters}
    assert:
      - {type: contains, value: definitely-not-present}
---
Tell me about {{ word }}.
"""


def test_evaluate_reports_per_case_and_overall(runtime):
    report = runtime.evaluate(make(EVAL_PROMPT))
    assert report["passed"] is False           # one case fails on purpose
    assert len(report["cases"]) == 2
    passing = next(c for c in report["cases"] if c["id"] == "pass-case")
    failing = next(c for c in report["cases"] if c["id"] == "fail-case")
    assert passing["passed"] is True
    assert failing["passed"] is False
    assert report["failed_assertions"] == 1
    assert report["score_ci"]["reason"] == "fewer than three usable cases"
    assert report["failure_attribution"] == [{
        "component_type": "output",
        "component": "final_output",
        "failure_count": 1,
        "cases": ["fail-case"],
        "evaluators": ["contains"],
    }]


def test_json_schema_assertion_against_echo_json(runtime):
    pf = make(
        "---\npromptfile: 1\nid: t/js\nmodel: {primary: echo/json}\n"
        "output:\n  schema:\n    type: object\n    required: [word]\n"
        "    properties:\n      word: {type: string}\n"
        "evals:\n  - id: c\n    input: {word: otters}\n"
        "    assert:\n      - {type: json_valid}\n      - {type: json_schema}\n---\nx"
    )
    assert runtime.evaluate(pf)["passed"] is True


def test_unknown_evaluator_fails_loudly_not_silently(runtime):
    pf = make(
        "---\npromptfile: 1\nid: t/unk\nmodel: {primary: echo/echo}\n"
        "evals:\n  - id: c\n    assert:\n      - {type: does_not_exist}\n---\nx"
    )
    report = runtime.evaluate(pf)
    assert report["passed"] is False
    assert "evaluator error" in report["cases"][0]["results"][0]["reason"]
    assert report["failure_attribution"][0]["component_type"] == "evaluator"


def test_llm_judge_without_a_judge_callable_fails_closed():
    from assay_core.builtins.evaluators import LLMJudgeEvaluator

    result = LLMJudgeEvaluator().evaluate("anything", assertion={"value": "good?"}, context={})
    assert result.passed is False


def test_aggregate_is_weighted():
    results = [
        EvalResult(passed=True, score=1.0, evaluator="a", weight=3),
        EvalResult(passed=False, score=0.0, evaluator="b", weight=1),
    ]
    summary = aggregate(results)
    assert summary["score"] == 0.75
    assert summary["passed"] is False
    assert summary["failed"] == 1


def test_aggregate_with_no_results_is_not_checked():
    summary = aggregate([])
    assert summary["passed"] is None
    assert summary["score"] is None
    assert summary["usable"] is False
    assert summary["total"] == 0


def test_eval_case_without_assertions_is_not_checked(runtime):
    pf = make(
        "---\npromptfile: 1\nid: t/empty-eval\nmodel: {primary: echo/echo}\n"
        "evals:\n  - id: no-assertions\n    input: {}\n---\nhello"
    )
    report = runtime.evaluate(pf)
    assert report["passed"] is None
    assert report["score"] is None
    assert report["usable"] is False
    assert report["unverified_cases"] == 1
    assert report["cases"][0]["passed"] is None


# -- stores ----------------------------------------------------------------


def test_file_store_put_get_list_delete(tmp_path):
    from assay_core.builtins.stores import FileStore

    store = FileStore(tmp_path)
    store.put(make(BASIC))
    assert list(store.list()) == ["t/basic"]
    assert store.get("t/basic").id == "t/basic"
    store.delete("t/basic")
    assert list(store.list()) == []


def test_file_store_rejects_traversal_ids(tmp_path):
    from assay_core.builtins.stores import FileStore
    from assay_core.errors import StoreError

    store = FileStore(tmp_path)
    for prompt_id in ("../escape", "a/../../escape", "a//b", "a/./b"):
        with pytest.raises(StoreError):
            store.path_for(prompt_id)


def test_file_store_rejects_prompt_path_outside_root(tmp_path):
    from assay_core.builtins.stores import FileStore
    from assay_core.errors import StoreError

    store = FileStore(tmp_path / "prompts")
    pf = make(BASIC)
    pf.path = tmp_path / "outside.prompt.md"
    with pytest.raises(StoreError):
        store.put(pf)
    assert not pf.path.exists()


def test_file_store_validates_before_writing(tmp_path):
    from assay_core.builtins.stores import FileStore
    from assay_core.errors import ValidationError

    store = FileStore(tmp_path)
    invalid = make(BASIC)
    invalid.data["status"] = "definitely-not-a-status"
    with pytest.raises(ValidationError) as raised:
        store.put(invalid)
    assert raised.value.errors
    assert not store.path_for(invalid.id).exists()


def test_file_store_refreshes_for_external_writes(tmp_path):
    from assay_core.builtins.stores import FileStore

    first = FileStore(tmp_path)
    second = FileStore(tmp_path)
    assert list(first.list()) == []
    second.put(make(BASIC))
    assert list(first.list()) == ["t/basic"]


def test_promptfile_save_is_atomic_and_leaves_no_temporary_file(tmp_path):
    pf = make(BASIC)
    target = tmp_path / "nested" / "basic.prompt.md"
    assert pf.save(target) == target.resolve()
    assert PromptFile.load(target).id == "t/basic"
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


def test_file_store_skips_unparseable_files_during_discovery(tmp_path):
    from assay_core.builtins.stores import FileStore

    (tmp_path / "good.prompt.md").write_text(BASIC, encoding="utf-8")
    (tmp_path / "broken.prompt.md").write_text("---\npromptfile: 99\nid: x\n---\n", encoding="utf-8")
    assert list(FileStore(tmp_path).list()) == ["t/basic"]


def test_memory_store_satisfies_the_same_contract():
    store = MemoryStore()
    store.put(make(BASIC), message="first")
    assert list(store.list()) == ["t/basic"]
    assert store.history("t/basic")[0]["message"] == "first"


def test_store_not_found_raises():
    from assay_core.errors import NotFound

    with pytest.raises(NotFound):
        MemoryStore().get("nope")
