from __future__ import annotations

import pytest

from assay import Client


PROMPT = """---
promptfile: 1
id: sdk/greet
model: {primary: echo/echo}
evals:
  - {id: one, input: {name: Ada}, assert: [{type: contains, value: Ada}]}
  - {id: two, input: {name: Grace}, assert: [{type: contains, value: Grace}]}
---
Hello {{ name }}.
"""

TOOL_PROMPT = """---
promptfile: 1
id: sdk/tool
model:
  primary: echo/agent
  provider_params:
    echo:
      script:
        - {tool: lookup, arguments: {id: 7}}
tools: [{name: lookup}]
---
Look up {{ subject }}.
"""


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "assay.yaml").write_text(
        "promptfile: 1\nname: sdk\nprompts: ./prompts\n", encoding="utf-8"
    )
    (tmp_path / "prompts" / "greet.prompt.md").write_text(PROMPT, encoding="utf-8")
    (tmp_path / "prompts" / "tool.prompt.md").write_text(TOOL_PROMPT, encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_embedded_client_streams_deltas_and_final_evidence(workspace):
    client = Client.local(str(workspace))
    events = [event async for event in client.stream("sdk/greet", {"name": "Ada"})]

    assert all(event["type"] == "delta" for event in events[:-1])
    assert events[-1]["type"] == "completed"
    assert "Ada" in "".join(event["delta"] for event in events[:-1])
    assert events[-1]["result"]["streaming"]["mode"] == "native"


@pytest.mark.asyncio
async def test_embedded_client_streams_portable_tool_call_events(workspace):
    client = Client.local(str(workspace))
    events = [event async for event in client.stream("sdk/tool", {"subject": "record"})]

    tool_event = next(event for event in events if event["type"] == "tool_call_delta")
    assert tool_event["tool_call"] == {
        "index": 0, "id": "echo-0", "name": "lookup", "arguments": {"id": 7},
    }
    assert events[-1]["result"]["tool_calls"] == [{
        "name": "lookup", "arguments": {"id": 7}, "id": "echo-0",
    }]


def test_embedded_client_exposes_bounded_evaluation(workspace):
    report = Client.local(str(workspace)).evaluate("sdk/greet", max_workers=2)
    assert report["passed"] is True
    assert report["execution"]["mode"] == "bounded_concurrent"
    assert report["execution"]["max_concurrency"] == 2


def test_remote_client_sends_snake_case_worker_query(monkeypatch):
    client = Client("https://assay.invalid")
    observed = {}

    def request(method, path, **kwargs):
        observed.update(method=method, path=path, **kwargs)
        return {"passed": True}

    monkeypatch.setattr(client, "_request", request)
    assert client.evaluate("sdk/greet", model="echo/echo", max_workers=3)["passed"] is True
    assert observed["params"] == {"model": "echo/echo", "max_workers": 3}


@pytest.mark.parametrize("value", [0, 33, True])
def test_sdk_rejects_invalid_worker_bounds(value):
    with pytest.raises(ValueError, match="between 1 and 32"):
        Client("https://assay.invalid").evaluate("sdk/greet", max_workers=value)
