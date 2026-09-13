"""Test-time compute is real, bounded, selected, and fully costed."""

from __future__ import annotations

import pytest

from assay_core import AgentRuntime, PromptFile, Runtime, Workspace
from assay_core.contracts import (
    CONTRACT_VERSION,
    Completion,
    ModelInfo,
    RenderedPrompt,
    Usage,
)
from assay_core.runtime import RunResult


class SequenceProvider:
    id = "sequence"
    contract_version = CONTRACT_VERSION

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.index = 0

    def capabilities(self, model):
        return frozenset({"text"})

    def list_models(self):
        return [ModelInfo(id="model", provider=self.id, capabilities=frozenset({"text"}))]

    def complete(self, prompt):
        text = self.outputs[self.index]
        self.index += 1
        return Completion(
            text=text,
            model="model",
            provider=self.id,
            usage=Usage(input_tokens=10, output_tokens=2),
            latency_ms=5,
            cost_usd=1.0,
        )


def _runtime(tmp_path, outputs):
    runtime = Runtime(workspace=Workspace(root=tmp_path), default_model="echo/echo")
    runtime.registry.register("assay.providers", "sequence", SequenceProvider(outputs))
    return runtime


def _prompt(*, selection="majority"):
    params = {"samples": 3, "selection": selection}
    if selection == "verifier":
        params["verifier"] = "judges/select"
    return PromptFile(
        data={
            "promptfile": 1,
            "id": "tests/sampled",
            "model": {"primary": "sequence/model", "params": params},
            "evals": [{"id": "answer", "assert": [{"type": "equals", "value": "A"}]}],
        },
        body="Answer.",
    )


def test_majority_selection_counts_text_and_aggregates_all_sample_cost(tmp_path):
    runtime = _runtime(tmp_path, ["B", "A", "A"])

    result = runtime.run(_prompt())

    assert result.text == "A"
    assert result.cost_usd == 3.0
    assert result.completion.usage.total_tokens == 36
    assert result.sampling["agreement"] == pytest.approx(2 / 3, abs=1e-6)
    assert result.sampling["selected_index"] == 1
    assert result.sampling["single_sample_cost_usd"] == 1.0
    assert result.sampling["cost_multiplier"] == 3.0
    assert all("output_sha256" in candidate for candidate in result.sampling["candidates"])
    assert all("output" not in candidate for candidate in result.sampling["candidates"])


def test_verifier_selection_uses_scores_and_includes_grading_cost(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path, ["A", "B", "C"])

    def score(verifier_ref, original, candidate, model_ref):
        value = {"A": 0.2, "B": 0.9, "C": 0.4}[candidate]
        completion = Completion(
            text=f'{{"score":{value}}}', model="judge", provider="sequence",
            usage=Usage(input_tokens=3, output_tokens=1), cost_usd=0.25,
        )
        run = RunResult(completion=completion, rendered=RenderedPrompt(messages=[]))
        return value, f"score {value}", run

    monkeypatch.setattr(runtime, "_score_with_verifier", score)
    result = runtime.run(_prompt(selection="verifier"))

    assert result.text == "B"
    assert result.sampling["scores"] == [0.2, 0.9, 0.4]
    assert result.sampling["selected_index"] == 1
    assert result.cost_usd == 3.75
    assert result.completion.usage.total_tokens == 48


def test_eval_report_pairs_accuracy_with_actual_and_single_sample_cost(tmp_path):
    runtime = _runtime(tmp_path, ["A", "B", "A"])

    report = runtime.evaluate(_prompt())

    assert report["score"] == 1.0
    assert report["accuracy_cost"]["total_cost_usd"] == 3.0
    assert report["accuracy_cost"]["single_sample_reference_cost_usd"] == 1.0
    assert report["accuracy_cost"]["incremental_test_time_cost_usd"] == 2.0
    assert report["accuracy_cost"]["cost_multiplier"] == 3.0
    assert "causal" in report["accuracy_cost"]["note"]


def test_agent_turns_also_use_sampling_and_record_evidence(tmp_path):
    harness = PromptFile.parse("""---
promptfile: 1
id: agents/sampled
kind: harness
model:
  primary: echo/agent
  params: { samples: 3, selection: majority }
  provider_params:
    echo:
      script:
        - { tool: mock.search, arguments: { query: retry } }
        - { text: done }
harness:
  max_iterations: 3
  control:
    mock_responses: { mock.search: result }
tools:
  - { ref: mock.search }
---
Investigate.
""")
    runtime = Runtime(workspace=Workspace(root=tmp_path), default_model="echo/agent")

    trajectory = AgentRuntime(runtime).run(harness)
    events = [event for event in trajectory.events if event["type"] == "test_time_compute"]

    assert trajectory.status == "completed"
    assert len(events) == 2
    assert all(event["samples_requested"] == 3 for event in events)
    assert all(event["agreement"] == 1.0 for event in events)
