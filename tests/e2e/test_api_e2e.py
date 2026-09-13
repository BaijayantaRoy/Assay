"""The REST API, against a real uvicorn process on a real port.

A TestClient would skip startup, the lifespan hook, port binding and teardown — which is
where server bugs live.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

pytestmark = pytest.mark.e2e


def _stream(url: str, payload: dict):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            assert response.headers.get_content_type() == "text/event-stream"
            events = []
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                events.append(data if data == "[DONE]" else json.loads(data))
            return response.status, events
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# The server starts and describes itself
# ---------------------------------------------------------------------------


def test_health_and_root(api_server, http):
    status, service = http("GET", f"{api_server}/health")
    assert status == 200
    assert service["legacy_api_enabled"] is False

    status, body = http("GET", f"{api_server}/v1/health")
    assert status == 200 and body["status"] == "ok"

    status, body = http("GET", f"{api_server}/v1/")
    assert status == 200
    assert body["spec"] == "promptfile-v1"
    assert body["surfaces"]["mcp"]


def test_legacy_database_api_is_not_exposed_by_default(api_server, http):
    for path in ("/intelligence/models", "/library/categories", "/projects"):
        status, _body = http("GET", f"{api_server}{path}")
        assert status == 404, f"deprecated compatibility route is enabled: {path}"


def test_openapi_is_served_and_documents_v1(api_server, http):
    status, spec = http("GET", f"{api_server}/openapi.json")
    assert status == 200
    v1 = [p for p in spec["paths"] if p.startswith("/v1")]
    assert len(v1) >= 25, f"only {len(v1)} v1 paths documented"
    for required in ("/v1/prompts", "/v1/harnesses", "/v1/loops",
                     "/v1/memory", "/v1/tokens", "/v1/judge/calibrate"):
        assert required in spec["paths"], f"{required} missing from OpenAPI"


def test_docs_page_renders(api_server, http):
    status, _ = http("GET", f"{api_server}/docs")
    assert status == 200


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def test_list_and_fetch_a_prompt(api_server, http):
    status, prompts = http("GET", f"{api_server}/v1/prompts")
    assert status == 200
    assert {p["id"] for p in prompts} >= {"e2e/greet", "e2e/agent", "e2e/loop"}

    status, detail = http("GET", f"{api_server}/v1/prompts/e2e/greet")
    assert status == 200
    assert detail["source"].startswith("---")     # the real file, not a rendering
    assert "name" in detail["variables"]


def test_render_then_run(api_server, http):
    status, rendered = http("POST", f"{api_server}/v1/prompts/e2e/greet/render",
                            {"variables": {"name": "Ada"}})
    assert status == 200
    assert "Ada" in rendered["messages"][0]["content"]

    status, result = http("POST", f"{api_server}/v1/prompts/e2e/greet/run",
                          {"variables": {"name": "Ada"}})
    assert status == 200
    assert "Ada" in result["output"]
    assert result["usage"]["total_tokens"] > 0


def test_stream_returns_ordered_deltas_and_final_run_evidence(api_server):
    status, events = _stream(
        f"{api_server}/v1/prompts/e2e/greet/stream",
        {"variables": {"name": "Ada"}},
    )
    assert status == 200
    assert events[-1] == "[DONE]"
    payloads = events[:-1]
    assert all(event["type"] == "delta" for event in payloads[:-1])
    assert payloads[-1]["type"] == "completed"
    assert "Ada" in "".join(event["delta"] for event in payloads[:-1])
    result = payloads[-1]["result"]
    assert result["usage"]["total_tokens"] > 0
    assert result["streaming"]["mode"] == "native"


def test_stream_guardrail_bypass_is_server_disabled_by_default(api_server):
    status, body = _stream(
        f"{api_server}/v1/prompts/e2e/greet/stream",
        {"variables": {"name": "Ada"}, "skip_guardrails": True},
    )
    assert status == 403
    assert body["detail"]["code"] == "assay.security.guardrail_bypass_disabled"


def test_evaluate_returns_a_ci_shaped_report(api_server, http):
    status, report = http(
        "POST", f"{api_server}/v1/prompts/e2e/greet/evaluate?max_workers=2"
    )
    assert status == 200
    assert report["passed"] is True
    assert report["cases"]
    assert report["execution"]["mode"] == "bounded_concurrent"
    # Report the bound actually exercised, never the larger requested number.
    assert report["execution"]["max_concurrency"] == 1

    status, invalid = http(
        "POST", f"{api_server}/v1/prompts/e2e/greet/evaluate?max_workers=33"
    )
    assert status == 422
    assert invalid["detail"]


def test_missing_prompt_is_404_with_a_structured_error(api_server, http):
    status, body = http("GET", f"{api_server}/v1/prompts/nope/nothing")
    assert status == 404
    assert body["detail"]["code"] == "assay.store.not_found"


def test_create_and_patch_round_trip(api_server, http):
    status, created = http("POST", f"{api_server}/v1/prompts", {
        "id": "e2e/created", "body": "Do {{ thing }}.", "description": "made over http",
    })
    assert status == 201 and created["version"] == 1

    status, patched = http("PATCH", f"{api_server}/v1/prompts/e2e/created",
                           {"status": "review"})
    assert status == 200
    assert patched["version"] == 2, "an edit must bump the revision counter"

    status, fetched = http("GET", f"{api_server}/v1/prompts/e2e/created")
    assert fetched["status"] == "review"


def test_invalid_create_is_rejected_before_it_is_written(api_server, http):
    status, _ = http("POST", f"{api_server}/v1/prompts",
                     {"id": "NOT VALID", "body": "x"})
    assert status == 422


# ---------------------------------------------------------------------------
# Agents and loops
# ---------------------------------------------------------------------------


def test_harness_run_returns_the_whole_trajectory(api_server, http):
    status, trajectory = http("POST", f"{api_server}/v1/harnesses/e2e/agent/run",
                              {"goal": "find the retry logic"})
    assert status == 200
    assert trajectory["status"] == "completed"
    assert "mock.search" in trajectory["tool_calls"]
    assert trajectory["steps"]
    assert "events" in trajectory


def test_harness_endpoint_rejects_a_plain_prompt(api_server, http):
    status, body = http("POST", f"{api_server}/v1/harnesses/e2e/greet/run", {})
    assert status == 400
    assert body["detail"]["code"] == "assay.kind_mismatch"


def test_loop_run_reports_verification(api_server, http):
    status, run = http("POST", f"{api_server}/v1/loops/e2e/loop/run", {})
    assert status == 200
    assert run["goal_met"] is True
    assert run["cycles"][0]["verified"] is True


def test_redteam_over_http_states_its_mode(api_server, http):
    status, report = http("POST", f"{api_server}/v1/harnesses/e2e/agent/redteam", {})
    assert status == 200
    assert report["usable"] is True
    assert report["attack_success_rate"] == 0.0
    assert report["mode"] == "scripted"
    assert "not model susceptibility" in report["mode_note"]


def test_corpus_is_exposed(api_server, http):
    status, corpus = http("GET", f"{api_server}/v1/redteam/corpus")
    assert status == 200
    assert corpus["count"] == 64
    assert sum(entry["category"] == "benign" for entry in corpus["attacks"]) == 12
    assert len(corpus["categories"]) == 27
    assert "benign" in corpus["categories"]


# ---------------------------------------------------------------------------
# Memory, disclosure, calibration
# ---------------------------------------------------------------------------


def test_memory_written_by_a_run_is_searchable(api_server, http):
    http("POST", f"{api_server}/v1/harnesses/e2e/agent/run", {"goal": "find the retry logic"})
    status, hits = http("GET", f"{api_server}/v1/memory/search?q=retry%20logic&namespace=e2e")
    assert status == 200
    assert hits["count"] >= 1


def test_tokens_and_index_agree(api_server, http):
    status, tokens = http("GET", f"{api_server}/v1/tokens")
    assert status == 200
    assert tokens["index"]["index_tokens"] > 0

    status, index = http("GET", f"{api_server}/v1/index")
    assert status == 200
    assert index["prompts"]
    assert index["namespaces"]


def test_calibration_endpoint_applies_the_two_stage_gate(api_server, http):
    """Perfect agreement must certify; noise must not."""
    good = [{"id": f"c{i}", "output": f"r{i}",
             "ratings": {"a": (i % 5) + 1, "b": (i % 5) + 1},
             "judge_score": (i % 5) + 1} for i in range(40)]
    status, report = http("POST", f"{api_server}/v1/judge/calibrate",
                          {"cases": good, "resamples": 100})
    assert status == 200
    assert report["certified"] is True
    assert report["rubric"]["ok"] and report["judge"]["ok"]

    noisy = [{"id": f"c{i}", "output": f"r{i}",
              "ratings": {"a": (i % 5) + 1, "b": ((i * 3) % 5) + 1},
              "judge_score": ((i * 7) % 5) + 1} for i in range(40)]
    status, report = http("POST", f"{api_server}/v1/judge/calibrate",
                          {"cases": noisy, "resamples": 100})
    assert status == 200
    assert report["certified"] is False
    assert report["failures"]


def test_too_few_cases_is_refused(api_server, http):
    tiny = [{"id": "c1", "ratings": {"a": 3, "b": 3}, "judge_score": 3}]
    status, _ = http("POST", f"{api_server}/v1/judge/calibrate",
                     {"cases": tiny, "resamples": 50})
    assert status == 422


def test_plugins_and_spec_are_introspectable(api_server, http):
    status, inventory = http("GET", f"{api_server}/v1/plugins")
    assert status == 200
    assert len(inventory["assay.providers"]) >= 5

    status, schema = http("GET", f"{api_server}/v1/spec")
    assert status == 200
    assert schema["title"] == "PromptFile v1"
