"""The MCP server, over real stdio to a real subprocess.

This is how every MCP client talks to it. Calling the handler functions in-process would
skip JSON-RPC framing, stdout discipline and the stderr-only logging rule — all of which
have broken real servers.
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.e2e


def rpc(id_, method, params=None):
    return {"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


def test_legacy_handshake_and_stateless_discover_both_work(mcp_call):
    """Clients are spread across revisions for a long time; both must be served."""
    responses = mcp_call(
        rpc(1, "initialize", {"protocolVersion": "2025-11-25",
                              "clientInfo": {"name": "e2e", "version": "1"}}),
        rpc(2, "server/discover"),
    )
    assert responses[1]["result"]["protocolVersion"] == "2025-11-25"
    assert responses[2]["result"]["protocolVersion"] == "2026-07-28"
    for i in (1, 2):
        caps = responses[i]["result"]["capabilities"]
        assert {"prompts", "resources", "tools"} <= set(caps)


def test_unknown_method_returns_method_not_found(mcp_call):
    responses = mcp_call(rpc(1, "nonexistent/method"))
    assert responses[1]["error"]["code"] == -32601


def test_a_bad_request_does_not_kill_the_server(mcp_call):
    """One malformed call must not take the session down."""
    responses = mcp_call(
        rpc(1, "prompts/get", {}),            # missing required 'name'
        rpc(2, "prompts/list"),               # must still be answered
    )
    assert "error" in responses[1]
    assert responses[2]["result"]["prompts"]


def test_stdout_carries_only_jsonrpc(mcp_call):
    """Diagnostics go to stderr. A stray print on stdout corrupts the protocol."""
    responses = mcp_call(rpc(1, "prompts/list"))
    assert responses[1]["jsonrpc"] == "2.0"


# ---------------------------------------------------------------------------
# Prompts and progressive disclosure
# ---------------------------------------------------------------------------


def test_prompts_list_is_tier_one_only(mcp_call):
    responses = mcp_call(rpc(1, "prompts/list"))
    result = responses[1]["result"]
    names = {p["name"] for p in result["prompts"]}
    assert {"e2e/greet", "e2e/agent"} <= names

    disclosure = result["_meta"]["dev.assay/disclosure"]
    assert disclosure["tier"] == 1
    assert disclosure["index_tokens"] < disclosure["naive_tokens"], (
        "tiering saved nothing; the index is as expensive as sending everything"
    )
    assert result["ttlMs"] > 0, "clients cannot cache without a TTL"


def test_prompts_list_declares_typed_arguments(mcp_call):
    responses = mcp_call(rpc(1, "prompts/list"))
    greet = next(p for p in responses[1]["result"]["prompts"] if p["name"] == "e2e/greet")
    names = {a["name"] for a in greet["arguments"]}
    assert "name" in names
    assert any(a["required"] for a in greet["arguments"])


def test_prompts_get_renders_with_arguments(mcp_call):
    responses = mcp_call(rpc(1, "prompts/get", {"name": "e2e/greet",
                                                "arguments": {"name": "Ada"}}))
    messages = responses[1]["result"]["messages"]
    assert "Ada" in messages[-1]["content"]["text"]


def test_namespace_map_is_present_for_orientation(mcp_call):
    responses = mcp_call(rpc(1, "prompts/list"))
    meta = responses[1]["result"]["_meta"]
    assert meta["dev.assay/namespaces"].get("e2e") == 3


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


def test_resources_include_the_spec_and_the_index(mcp_call):
    responses = mcp_call(rpc(1, "resources/list"))
    uris = {r["uri"] for r in responses[1]["result"]["resources"]}
    assert "assay://spec/promptfile-v1" in uris
    assert "assay://index" in uris
    assert "assay://models" in uris


def test_reading_the_index_returns_valid_json(mcp_call):
    responses = mcp_call(rpc(1, "resources/read", {"uri": "assay://index"}))
    payload = json.loads(responses[1]["result"]["contents"][0]["text"])
    assert payload["prompts"]
    assert "disclosure" in payload


def test_reading_a_prompt_returns_its_source(mcp_call):
    responses = mcp_call(rpc(1, "resources/read", {"uri": "assay://prompt/e2e/greet"}))
    text = responses[1]["result"]["contents"][0]["text"]
    assert text.startswith("---") and "id: e2e/greet" in text


def test_unknown_resource_uri_is_an_error(mcp_call):
    responses = mcp_call(rpc(1, "resources/read", {"uri": "assay://nope"}))
    assert "error" in responses[1]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def test_tools_are_declared_with_full_json_schema(mcp_call):
    responses = mcp_call(rpc(1, "tools/list"))
    tools = {t["name"]: t for t in responses[1]["result"]["tools"]}
    assert {"assay_search", "assay_get", "assay_render", "assay_run",
            "assay_test", "assay_lint", "assay_create"} <= set(tools)
    schema = tools["assay_search"]["inputSchema"]
    assert schema["$schema"].endswith("2020-12/schema")
    assert tools["assay_search"]["annotations"]["readOnlyHint"] is True


def test_search_then_render_then_run(mcp_call):
    responses = mcp_call(
        rpc(1, "tools/call", {"name": "assay_search", "arguments": {"query": "greet"}}),
        rpc(2, "tools/call", {"name": "assay_render",
                              "arguments": {"id": "e2e/greet", "variables": {"name": "Ada"}}}),
        rpc(3, "tools/call", {"name": "assay_run",
                              "arguments": {"id": "e2e/greet", "variables": {"name": "Ada"}}}),
    )
    assert responses[1]["result"]["structuredContent"]["count"] >= 1
    assert "Ada" in responses[2]["result"]["structuredContent"]["messages"][0]["content"]
    assert "Ada" in responses[3]["result"]["structuredContent"]["output"]


def test_assay_test_gives_an_agent_a_way_to_verify_its_own_edit(mcp_call):
    """The pairing that makes the server useful: author, then prove nothing regressed."""
    responses = mcp_call(
        rpc(1, "tools/call", {"name": "assay_create", "arguments": {
            "id": "e2e/agent-made", "body": "Summarise {{ text }}.",
            "description": "created through MCP"}}),
        rpc(2, "tools/call", {"name": "assay_test", "arguments": {}}),
    )
    assert responses[1]["result"]["structuredContent"]["id"] == "e2e/agent-made"
    verification = responses[2]["result"]["structuredContent"]
    assert verification["passed"] is None
    assert verification["prompts_unverified"] >= 1
    created_report = next(
        report for report in verification["reports"]
        if report["prompt_id"] == "e2e/agent-made"
    )
    assert created_report["passed"] is None
    assert created_report["error"] == "no eval cases defined"


def test_assay_test_advertises_and_honours_bounded_workers(mcp_call):
    listed = mcp_call(rpc(1, "tools/list"))
    tools = {tool["name"]: tool for tool in listed[1]["result"]["tools"]}
    workers = tools["assay_test"]["inputSchema"]["properties"]["max_workers"]
    assert workers["minimum"] == 1 and workers["maximum"] == 32

    response = mcp_call(rpc(2, "tools/call", {
        "name": "assay_test",
        "arguments": {"id": "e2e/greet", "max_workers": 2},
    }))
    payload = response[2]["result"]["structuredContent"]
    assert payload["passed"] is True
    assert payload["reports"][0]["execution"]["mode"] == "bounded_concurrent"


def test_a_failing_tool_call_is_reported_not_raised(mcp_call):
    responses = mcp_call(rpc(1, "tools/call", {"name": "assay_get",
                                               "arguments": {"id": "does/not-exist"}}))
    assert responses[1]["result"]["isError"] is True


def test_unknown_tool_is_an_error(mcp_call):
    responses = mcp_call(rpc(1, "tools/call", {"name": "not_a_tool", "arguments": {}}))
    assert "error" in responses[1] or responses[1]["result"]["isError"]


def test_batch_requests_are_all_answered(mcp_call):
    responses = mcp_call(
        rpc(1, "prompts/list"), rpc(2, "tools/list"),
        rpc(3, "resources/list"), rpc(4, "ping"),
    )
    assert set(responses) == {1, 2, 3, 4}
    assert all("result" in r for r in responses.values())
