"""Cross-surface parity.

The architecture claims the CLI, the REST API and the MCP server are "three faces of one
engine" and therefore cannot drift apart. That is a claim, and claims need tests.

It has already been false once: `assay_test` over MCP did not dispatch by artifact kind, so
harnesses were evaluated through the plain prompt runtime and every trajectory assertion
failed for the wrong reason. The CLI got it right, the MCP server did not, and nothing
noticed until a test compared them. These tests exist so that class of bug is caught by
CI rather than by a user.
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.e2e


def rpc(id_, method, params=None):
    return {"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}


# ---------------------------------------------------------------------------
# Same artifact, same answer, whichever door you come through
# ---------------------------------------------------------------------------


def test_render_is_identical_across_cli_api_and_mcp(run_assay_shared, api_server, http, mcp_call_shared):
    """A prompt rendered three ways must produce byte-identical messages."""
    variables = {"name": "Ada"}

    code, out, _ = run_assay_shared("render", "e2e/greet", "-v", "name=Ada", "--json")
    assert code == 0
    cli_text = json.loads(out)["messages"][0]["content"]

    _, rendered = http("POST", f"{api_server}/v1/prompts/e2e/greet/render",
                       {"variables": variables})
    api_text = rendered["messages"][0]["content"]

    responses = mcp_call_shared(rpc(1, "prompts/get",
                             {"name": "e2e/greet", "arguments": variables}))
    mcp_text = responses[1]["result"]["messages"][-1]["content"]["text"]

    assert cli_text == api_text == mcp_text, (
        "the surfaces disagree about what this prompt renders to:\n"
        f"  cli: {cli_text!r}\n  api: {api_text!r}\n  mcp: {mcp_text!r}"
    )


def test_run_output_is_identical_across_surfaces(run_assay_shared, api_server, http, mcp_call_shared):
    code, out, _ = run_assay_shared("run", "e2e/greet", "-v", "name=Ada", "--json")
    cli_output = json.loads(out)["output"]

    _, result = http("POST", f"{api_server}/v1/prompts/e2e/greet/run",
                     {"variables": {"name": "Ada"}})
    api_output = result["output"]

    responses = mcp_call_shared(rpc(1, "tools/call", {
        "name": "assay_run", "arguments": {"id": "e2e/greet", "variables": {"name": "Ada"}}}))
    mcp_output = responses[1]["result"]["structuredContent"]["output"]

    assert cli_output == api_output == mcp_output


def test_every_surface_lists_the_same_prompts(run_assay_shared, api_server, http, mcp_call_shared):
    code, out, _ = run_assay_shared("ls", "--json")
    cli_ids = {p["id"] for p in json.loads(out)["prompts"]}

    _, prompts = http("GET", f"{api_server}/v1/prompts")
    api_ids = {p["id"] for p in prompts}

    responses = mcp_call_shared(rpc(1, "prompts/list"))
    mcp_ids = {p["name"] for p in responses[1]["result"]["prompts"]}

    assert cli_ids == api_ids == mcp_ids


# ---------------------------------------------------------------------------
# Kind dispatch — the bug this suite was written after
# ---------------------------------------------------------------------------


def test_harness_evals_pass_on_every_surface(run_assay_shared, api_server, http, mcp_call_shared):
    """A harness must be evaluated *as a harness* wherever it is invoked.

    Run through the plain prompt runtime it produces no trajectory, so every trajectory
    assertion fails — and an agent using MCP to check its own edit would be told it broke
    something it did not.
    """
    code, out, _ = run_assay_shared("test", "e2e/agent", "--json")
    cli_passed = json.loads(out)["passed"]

    _, report = http("POST", f"{api_server}/v1/harnesses/e2e/agent/evaluate")
    api_passed = report["passed"]

    responses = mcp_call_shared(rpc(1, "tools/call",
                             {"name": "assay_test", "arguments": {"id": "e2e/agent"}}))
    mcp_passed = responses[1]["result"]["structuredContent"]["passed"]

    assert cli_passed is True
    assert api_passed is True
    assert mcp_passed is True, "MCP evaluated the harness as a plain prompt"


def test_whole_workspace_test_agrees_across_cli_and_mcp(run_assay_shared, mcp_call_shared):
    """`assay test` with no argument covers prompts, harnesses and loops together."""
    code, out, _ = run_assay_shared("test", "--json")
    cli = json.loads(out)

    responses = mcp_call_shared(rpc(1, "tools/call", {"name": "assay_test", "arguments": {}}))
    mcp = responses[1]["result"]["structuredContent"]

    assert cli["passed"] == mcp["passed"]
    assert cli["unverified"] == mcp["prompts_unverified"]
    assert cli["prompts"] - cli["unverified"] == mcp["prompts_tested"], (
        "the surfaces disagree about how many artifacts carry executable evals"
    )
    assert cli["passed"] is (None if cli["unverified"] else True), (
        "an unverified artifact must make the workspace result 'not checked', not passed"
    )


def test_harness_run_produces_a_trajectory_on_both_api_and_mcp(api_server, http, mcp_call_shared):
    _, api_trajectory = http("POST", f"{api_server}/v1/harnesses/e2e/agent/run",
                             {"goal": "find the retry logic"})
    responses = mcp_call_shared(rpc(1, "tools/call", {
        "name": "assay_run", "arguments": {"id": "e2e/agent",
                                         "variables": {"goal": "find the retry logic"}}}))
    mcp_trajectory = responses[1]["result"]["structuredContent"]

    for label, trajectory in (("api", api_trajectory), ("mcp", mcp_trajectory)):
        assert trajectory.get("tool_calls"), f"{label} returned no trajectory"
        assert trajectory["status"] == "completed", label


# ---------------------------------------------------------------------------
# Shared vocabulary
# ---------------------------------------------------------------------------


def test_plugin_inventory_matches_across_cli_and_api(run_assay_shared, api_server, http):
    code, out, _ = run_assay_shared("plugins", "--json")
    cli = json.loads(out)
    _, api = http("GET", f"{api_server}/v1/plugins")

    for group in ("assay.providers", "assay.evaluators", "assay.tools", "assay.memory"):
        assert {p["name"] for p in cli[group]} == {p["name"] for p in api[group]}, group


def test_the_spec_served_matches_the_spec_on_disk(api_server, http, run_assay_shared):
    code, out, _ = run_assay_shared("spec", "show", "--json")
    _, served = http("GET", f"{api_server}/v1/spec")
    assert json.loads(out)["title"] == served["title"] == "PromptFile v1"


def test_token_accounting_agrees_between_cli_and_api(run_assay_shared, api_server, http):
    code, out, _ = run_assay_shared("tokens", "--json")
    cli = json.loads(out)
    _, api = http("GET", f"{api_server}/v1/tokens")
    assert cli["prompts"] == api["prompts"]
    assert cli["index"]["index_tokens"] == api["index"]["index_tokens"]


def test_a_prompt_created_on_one_surface_is_visible_on_the_others(
    run_assay_shared, api_server, http, mcp_call_shared
):
    """Files are the shared substrate; every surface reads the same directory."""
    status, _ = http("POST", f"{api_server}/v1/prompts", {
        "id": "e2e/cross-surface", "body": "Do {{ thing }}.",
        "description": "created over http",
    })
    assert status == 201

    code, out, _ = run_assay_shared("ls", "--json")
    assert "e2e/cross-surface" in {p["id"] for p in json.loads(out)["prompts"]}

    responses = mcp_call_shared(rpc(1, "prompts/list"))
    assert "e2e/cross-surface" in {p["name"] for p in responses[1]["result"]["prompts"]}
