from __future__ import annotations

import base64
import json

import httpx
import pytest
import yaml

from assay_core.builtins.importers import (
    DotpromptImporter,
    ImportSource,
    LangfuseImporter,
    MessagesImporter,
    PomlImporter,
    PromptfooImporter,
    PromptLayerImporter,
    load_import_source,
    load_registry_source,
)
from assay_core.errors import ValidationError


def _source(tmp_path, document):
    path = tmp_path / "promptfooconfig.yaml"
    text = yaml.safe_dump(document, sort_keys=False)
    path.write_text(text, encoding="utf-8")
    return ImportSource(path=path, text=text, document=document, prefix="migrated")


def test_promptfoo_import_preserves_supported_tests_and_honest_gaps(tmp_path):
    source = _source(tmp_path, {
        "$schema": "https://promptfoo.dev/config-schema.json",
        "description": "Translation quality",
        "prompts": [{
            "id": "translate-v1", "label": "French Translator",
            "raw": "Translate {{ text }} to French.",
        }],
        "providers": [
            {"id": "openai:gpt-5-mini", "config": {
                "temperature": 0.2, "apiKey": "must-not-be-copied",
            }},
            "anthropic:messages:claude-sonnet-4-6",
        ],
        "tests": [{
            "description": "says bonjour",
            "vars": {"text": "hello"},
            "assert": [
                {"type": "icontains", "value": "bonjour"},
                {"type": "javascript", "value": "secret evaluator code"},
            ],
        }],
    })

    imported = PromptfooImporter().to_promptfiles(source)

    assert len(imported) == 1
    prompt = imported[0]
    assert prompt.id == "migrated/french-translator"
    assert prompt.model_ref == "openai/gpt-5-mini"
    assert prompt.fallbacks == ["anthropic/claude-sonnet-4-6"]
    assert prompt.params == {"temperature": 0.2}
    assert prompt.evals[0]["assert"] == [
        {"type": "contains", "ignore_case": True, "value": "bonjour"}
    ]
    assert prompt.evals[0]["x-promptfoo-assertions"][0]["type"] == "javascript"
    assert any("not translated" in warning for warning in prompt.extensions["x-import"]["warnings"])
    assert "must-not-be-copied" not in prompt.to_text()
    assert prompt.validate() == []


def test_prompt_filters_apply_to_the_matching_imported_prompt(tmp_path):
    source = _source(tmp_path, {
        "prompts": [
            {"id": "factual", "label": "Factual", "raw": "Answer {{q}}"},
            {"id": "creative", "label": "Creative", "raw": "Imagine {{q}}"},
        ],
        "providers": "openai:gpt-5-mini",
        "tests": [{
            "prompts": ["Factual"], "vars": {"q": "capital?"},
            "assert": [{"type": "contains", "value": "Paris"}],
        }],
    })

    factual, creative = PromptfooImporter().to_promptfiles(source)

    assert len(factual.evals) == 1
    assert creative.evals == []


def test_local_prompt_reference_is_resolved_but_cannot_escape_config_dir(tmp_path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Hello {{name}}", encoding="utf-8")
    valid = _source(tmp_path, {
        "prompts": ["file://prompt.txt"], "providers": ["openai:gpt-5-mini"],
    })
    assert PromptfooImporter().to_promptfiles(valid)[0].body == "Hello {{name}}"

    invalid = _source(tmp_path, {
        "prompts": ["file://../outside.txt"], "providers": ["openai:gpt-5-mini"],
    })
    with pytest.raises(ValidationError, match="escapes"):
        PromptfooImporter().to_promptfiles(invalid)


def test_load_import_source_parses_yaml_and_detects_promptfoo(tmp_path):
    path = tmp_path / "promptfooconfig.yaml"
    path.write_text("prompts: ['hello']\nproviders: [openai:gpt-5-mini]\n", encoding="utf-8")
    source = load_import_source(path)
    assert PromptfooImporter().detect(source) is True


def test_openai_message_request_imports_roles_model_and_content_parts(tmp_path):
    source = _source(tmp_path, {
        "model": "gpt-5-mini",
        "instructions": "Answer tersely for {{audience}}.",
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Describe this"},
                {"type": "input_image", "image_url": "https://example.test/image.png"},
            ],
        }],
        "temperature": 0.1,
        "store": False,
    })

    prompt = MessagesImporter().to_promptfiles(source)[0]

    assert prompt.model_ref == "openai/gpt-5-mini"
    assert prompt.messages[0] == {"role": "developer", "content": "Answer tersely for {{audience}}."}
    assert prompt.messages[1]["content"] == [
        {"type": "text", "text": "Describe this"},
        {"type": "image", "ref": "https://example.test/image.png"},
    ]
    assert prompt.params == {"temperature": 0.1}
    assert prompt.evals == []
    assert "store" in prompt.extensions["x-import"]["untranslated_top_level_fields"]
    assert any("unverified" in warning for warning in prompt.extensions["x-import"]["warnings"])
    assert prompt.validate() == []


def test_anthropic_system_and_messages_import_without_inventing_evals(tmp_path):
    source = _source(tmp_path, {
        "model": "claude-sonnet-4-6",
        "system": "You are careful.",
        "messages": [
            {"role": "user", "content": "Question: {{question}}"},
            {"role": "assistant", "content": "The answer is"},
        ],
        "max_tokens": 200,
    })

    prompt = MessagesImporter().to_promptfiles(source)[0]

    assert prompt.model_ref == "anthropic/claude-sonnet-4-6"
    assert [message["role"] for message in prompt.messages] == ["system", "user", "assistant"]
    assert prompt.evals == []
    assert prompt.status == "draft"


def test_dotprompt_simple_template_and_picoschema_become_executable_promptfile(tmp_path):
    path = tmp_path / "welcome.prompt"
    path.write_text(
        "---\n"
        "model: googleai/gemini-2.5-flash\n"
        "config: {temperature: 0.3, topK: 20, apiKey: never-copy}\n"
        "input:\n"
        "  schema:\n"
        "    location: string\n"
        "    style?: string\n"
        "output:\n"
        "  schema:\n"
        "    greeting: string\n"
        "---\n"
        "Welcome the guest at {{location}} in a {{style}} style.\n",
        encoding="utf-8",
    )

    source = load_import_source(path, prefix="genkit")
    prompt = DotpromptImporter().to_promptfiles(source)[0]

    assert prompt.id == "genkit/welcome"
    assert prompt.model_ref == "google/gemini-2.5-flash"
    assert prompt.renderer_id == "jinja2"
    assert prompt.params == {"temperature": 0.3, "top_k": 20}
    assert prompt.input_schema["required"] == ["location"]
    assert "style" in prompt.input_schema["properties"]
    assert prompt.output_schema["required"] == ["greeting"]
    assert "never-copy" not in prompt.to_text()
    assert prompt.validate() == []


def test_dotprompt_handlebars_helpers_are_preserved_but_not_claimed_executable(tmp_path):
    path = tmp_path / "conditional.prompt"
    path.write_text(
        "---\nmodel: vertexai/gemini-2.5-flash\n---\n"
        "Hello {{#if name}}{{name}}{{else}}friend{{/if}}.",
        encoding="utf-8",
    )

    prompt = DotpromptImporter().to_promptfiles(load_import_source(path))[0]

    assert prompt.renderer_id == "none"
    assert prompt.extensions["x-import"]["template_executable"] is False
    assert prompt.required_capabilities == frozenset({"dotprompt-runtime"})
    assert any("preserved literally" in warning for warning in prompt.extensions["x-import"]["warnings"])
    assert "{{#if name}}" in prompt.body


def test_poml_static_subset_becomes_executable_messages(tmp_path):
    path = tmp_path / "welcome.poml"
    path.write_text(
        '<poml><meta><runtime model="openai/gpt-5-mini" temperature="0.2" />'
        '<output-schema parser="json">'
        '{"type":"object","properties":{"answer":{"type":"string"}}}'
        "</output-schema></meta>"
        '<system-msg>You are precise.</system-msg><role caption="Role">'
        "Help {{user.name}}.</role><task>Return JSON.</task></poml>",
        encoding="utf-8",
    )

    prompt = PomlImporter().to_promptfiles(load_import_source(path, prefix="microsoft"))[0]

    assert prompt.id == "microsoft/welcome"
    assert prompt.renderer_id == "jinja2"
    assert prompt.model_ref == "openai/gpt-5-mini"
    assert prompt.params == {"temperature": 0.2}
    assert prompt.messages == [
        {"role": "system", "content": "You are precise."},
        {"role": "user", "content": "# Role\n\nHelp {{user.name}}.\n\n# Task\n\nReturn JSON."},
    ]
    assert "user" in prompt.input_schema["properties"]
    assert prompt.output_schema["properties"]["answer"]["type"] == "string"
    assert prompt.evals == []
    assert prompt.extensions["x-import"]["template_executable"] is True
    assert any("unverified" in warning for warning in prompt.extensions["x-import"]["warnings"])
    assert prompt.validate() == []


@pytest.mark.parametrize(
    "dynamic_source",
    [
        '<poml><p if="user.isAdmin">Secret for {{user.name}}</p></poml>',
        '<poml><p>{{ users.map(user => user.name).join(", ") }}</p></poml>',
        '<poml><tool-definition name="lookup" /></poml>',
        '<poml><list><item>One</item></list></poml>',
    ],
)
def test_poml_runtime_semantics_are_preserved_but_not_claimed_executable(
    tmp_path, dynamic_source
):
    path = tmp_path / "dynamic.poml"
    path.write_text(dynamic_source, encoding="utf-8")

    prompt = PomlImporter().to_promptfiles(load_import_source(path))[0]

    assert prompt.renderer_id == "none"
    assert prompt.body == dynamic_source
    assert "messages" not in prompt.data
    assert prompt.required_capabilities == frozenset({"poml-runtime"})
    assert prompt.extensions["x-import"]["template_executable"] is False
    assert any("not claimed" in warning for warning in prompt.extensions["x-import"]["warnings"])
    assert prompt.validate() == []


def test_poml_rejects_dtd_and_entities(tmp_path):
    path = tmp_path / "unsafe.poml"
    path.write_text(
        '<!DOCTYPE poml [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        "<poml><p>&xxe;</p></poml>",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="DTD or entity"):
        PomlImporter().to_promptfiles(load_import_source(path))


def test_import_source_refuses_files_larger_than_ten_mib(tmp_path):
    path = tmp_path / "oversized.poml"
    path.write_bytes(b" " * (10 * 1024 * 1024 + 1))

    with pytest.raises(ValidationError, match="larger than 10 MiB"):
        load_import_source(path)


def test_langfuse_registry_fetch_uses_basic_auth_without_persisting_credentials():
    payload = {
        "name": "team/greeting",
        "type": "text",
        "prompt": "Hello {{name}}",
        "version": 7,
        "labels": ["production"],
        "config": {"model": "gpt-5-mini", "temperature": 0.2},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.raw_path.split(b"?", 1)[0].endswith(b"/team%2Fgreeting")
        assert request.url.params.get("label") == "production"
        expected = base64.b64encode(b"public:secret").decode()
        assert request.headers["Authorization"] == f"Basic {expected}"
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        source = load_registry_source(
            "langfuse://team/greeting",
            prefix="remote",
            label="production",
            environ={"LANGFUSE_PUBLIC_KEY": "public", "LANGFUSE_SECRET_KEY": "secret"},
            client=client,
        )

    assert source.metadata["source_uri"] == "langfuse://team/greeting"
    assert "public" not in json.dumps(source.metadata)
    assert "secret" not in json.dumps(source.metadata)
    prompt = LangfuseImporter().to_promptfiles(source)[0]
    assert prompt.id == "remote/team-greeting"
    assert prompt.version == 7
    assert prompt.model_ref == "openai/gpt-5-mini"
    assert prompt.params == {"temperature": 0.2}
    assert prompt.renderer_id == "jinja2"
    assert prompt.required_capabilities == frozenset()
    assert "name" in prompt.input_schema["properties"]
    assert prompt.validate() == []


def test_langfuse_runtime_features_are_capability_gated_and_secret_values_scrubbed(tmp_path):
    payload = {
        "name": "composed",
        "type": "chat",
        "prompt": [
            {"role": "system", "content": "@@@langfusePrompt:name=policy|label=prod@@@"},
            {"role": "user", "content": "Question: {{question}}"},
        ],
        "config": {
            "model": "anthropic/claude-sonnet-4-6",
            "temperature": 0,
            "api_key": "never-copy-this",
            "tools": [{"name": "lookup"}],
        },
    }
    source = _source(tmp_path, payload)

    prompt = LangfuseImporter().to_promptfiles(source)[0]

    assert prompt.renderer_id == "none"
    assert prompt.required_capabilities == frozenset({"langfuse-runtime"})
    assert "never-copy-this" not in prompt.to_text()
    assert prompt.extensions["x-langfuse"]["untranslated_config_fields"] == [
        "api_key",
        "tools",
    ]
    assert prompt.evals == []
    assert prompt.validate() == []


def test_promptlayer_registry_fetch_uses_api_key_without_persisting_it():
    payload = {
        "success": True,
        "id": 17,
        "prompt_name": "support-response",
        "version": 2,
        "workspace_id": 42,
        "prompt_template": {
            "type": "chat",
            "template_format": "f-string",
            "messages": [
                {"role": "system", "content": [{"type": "text", "text": "Be helpful."}]},
                {"role": "user", "content": [{"type": "text", "text": "Help {name}."}]},
            ],
        },
        "metadata": {
            "model": {
                "provider": "openai",
                "name": "gpt-5-mini",
                "parameters": {"temperature": 0.1},
            }
        },
        "tags": ["support"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/support-response")
        assert request.url.params.get("version") == "2"
        assert request.headers["X-API-KEY"] == "pl-secret"
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        source = load_registry_source(
            "promptlayer://support-response",
            version=2,
            environ={"PROMPTLAYER_API_KEY": "pl-secret"},
            client=client,
        )

    assert "pl-secret" not in json.dumps(source.metadata)
    prompt = PromptLayerImporter().to_promptfiles(source)[0]
    assert prompt.id == "imported/support-response"
    assert prompt.version == 2
    assert prompt.renderer_id == "fstring"
    assert prompt.model_ref == "openai/gpt-5-mini"
    assert prompt.params == {"temperature": 0.1}
    assert prompt.messages[-1]["content"] == "Help {name}."
    assert "name" in prompt.input_schema["properties"]
    assert prompt.required_capabilities == frozenset()
    assert prompt.validate() == []


def test_promptlayer_unresolved_snippets_and_unknown_params_are_capability_gated(tmp_path):
    payload = {
        "prompt_name": "dynamic",
        "version": 3,
        "prompt_template": {
            "type": "completion",
            "template_format": "jinja2",
            "content": [{"type": "text", "text": "@@@policy@@@ Hi {{name}}"}],
        },
        "metadata": {
            "model": {
                "provider": "anthropic",
                "name": "claude-sonnet-4-6",
                "parameters": {"thinking": {"type": "enabled"}},
            }
        },
    }

    prompt = PromptLayerImporter().to_promptfiles(_source(tmp_path, payload))[0]

    assert prompt.renderer_id == "none"
    assert prompt.required_capabilities == frozenset({"promptlayer-runtime"})
    assert prompt.extensions["x-promptlayer"]["untranslated_model_parameter_fields"] == [
        "thinking"
    ]
    assert prompt.evals == []
    assert prompt.validate() == []


def test_registry_fetch_rejects_unsafe_origins_conflicting_selectors_and_large_responses():
    env = {"PROMPTLAYER_API_KEY": "key"}
    with pytest.raises(ValidationError, match="must use HTTPS"):
        load_registry_source(
            "promptlayer://example", base_url="http://registry.example", environ=env
        )
    with pytest.raises(ValidationError, match="mutually exclusive"):
        load_registry_source(
            "promptlayer://example", label="prod", version=2, environ=env
        )

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Length": str(10 * 1024 * 1024 + 1)},
            content=b"{}",
        )
    )
    with (
        httpx.Client(transport=transport) as client,
        pytest.raises(ValidationError, match="larger than 10 MiB"),
    ):
        load_registry_source("promptlayer://example", environ=env, client=client)
