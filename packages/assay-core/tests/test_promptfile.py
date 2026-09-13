"""PromptFile spec conformance.

These tests are the enforcement mechanism for the promises in
``docs/architecture/adr/0004-compatibility-policy.md``. If the round-trip tests fail,
the forward-compatibility guarantee is broken and the version claim is false.
"""

from __future__ import annotations

import json

import pytest
import yaml
from hypothesis import given, settings, strategies as st

from assay_core import PromptFile, UnsupportedSpecVersion, ValidationError
from assay_core.promptfile import discover

MINIMAL = """---
promptfile: 1
id: t/minimal
---
Hello {{ name }}.
"""

RICH = """---
promptfile: 1
id: t/rich
name: Rich
description: Everything at once.
version: 4
kind: prompt
status: stable
tags: [a, b]
requires:
  capabilities: [json_mode]
  min_context_tokens: 8000
engine:
  template: jinja2
  strict: true
input:
  schema:
    type: object
    required: [topic]
    properties:
      topic: {type: string}
output:
  format: json
model:
  primary: echo/json
  fallbacks: [echo/echo]
  params: {temperature: 0}
  provider_params:
    anthropic: {thinking: {type: enabled}}
messages:
  - role: system
    content: Be terse.
    cache: true
  - role: user
    content: "About {{ topic }}."
evals:
  - id: case-1
    input: {topic: otters}
    assert:
      - {type: json_valid}
guardrails:
  - {type: max_length, stage: output, action: warn, config: {max_chars: 100000}}
provenance:
  imported_from: dotprompt
x-vendor-thing:
  nested: {deeply: true}
  list: [1, 2, 3]
x-another: plain-string
---

Body that should be ignored because messages exist.
"""


# -- parsing ---------------------------------------------------------------


def test_minimal_parses():
    pf = PromptFile.parse(MINIMAL)
    assert pf.id == "t/minimal"
    assert pf.version == 1          # defaults applied
    assert pf.kind == "prompt"
    assert pf.status == "draft"
    assert pf.renderer_id == "jinja2"
    assert pf.body.strip() == "Hello {{ name }}."


def test_messages_take_precedence_over_body():
    pf = PromptFile.parse(RICH)
    assert len(pf.messages) == 2
    assert pf.messages[0]["role"] == "system"
    assert pf.messages[0]["cache"] is True


def test_body_becomes_a_user_message_when_no_messages():
    pf = PromptFile.parse(MINIMAL)
    assert pf.messages == [{"role": "user", "content": "Hello {{ name }}."}]


def test_missing_spec_version_is_rejected():
    with pytest.raises(ValidationError):
        PromptFile.parse("---\nid: t/x\n---\nbody")


def test_future_spec_version_is_refused_not_guessed():
    """Conformance rule 1: refuse a major version we do not implement."""
    with pytest.raises(UnsupportedSpecVersion) as exc:
        PromptFile.parse("---\npromptfile: 99\nid: t/x\n---\nbody")
    assert exc.value.context["file_version"] == 99


def test_missing_frontmatter_is_a_parse_error():
    from assay_core.errors import ParseError

    with pytest.raises(ParseError):
        PromptFile.parse("just a body, no frontmatter")


# -- round-trip (the load-bearing guarantee) -------------------------------


def test_round_trip_preserves_unknown_extension_keys():
    """Conformance rule 3: writers MUST preserve keys they do not understand."""
    pf = PromptFile.parse(RICH)
    reparsed = PromptFile.parse(pf.to_text())
    assert reparsed.data["x-vendor-thing"] == {
        "nested": {"deeply": True}, "list": [1, 2, 3],
    }
    assert reparsed.data["x-another"] == "plain-string"
    assert reparsed.extensions.keys() == {"x-vendor-thing", "x-another"}


def test_round_trip_is_byte_stable():
    """parse → write → parse → write must be a fixed point."""
    once = PromptFile.parse(RICH).to_text()
    twice = PromptFile.parse(once).to_text()
    assert once == twice


def test_round_trip_preserves_an_entirely_unknown_top_level_key():
    """A field added by a *newer* tool must survive an *older* tool rewriting the file."""
    source = MINIMAL.replace("id: t/minimal", "id: t/minimal\nfuture_field: {a: 1}")
    pf = PromptFile.parse(source)
    assert PromptFile.parse(pf.to_text()).data["future_field"] == {"a": 1}


_JSON_SCALAR = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**31), max_value=2**31 - 1),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),
        max_size=40,
    ),
)
_JSON_VALUE = st.recursive(
    _JSON_SCALAR,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(
            st.text(
                alphabet=st.characters(blacklist_categories=("Cs",)),
                min_size=1,
                max_size=16,
            ),
            children,
            max_size=5,
        ),
    ),
    max_leaves=20,
)


@settings(max_examples=100, deadline=None)
@given(value=_JSON_VALUE)
def test_unknown_json_values_round_trip_across_every_encoding(value):
    """Generated future fields must survive Markdown, YAML, and JSON writers exactly."""
    original = PromptFile(
        data={"promptfile": 1, "id": "property/future", "future_field": value},
        body="Generated body.",
    )

    for fmt in ("md", "yaml", "json"):
        once = original.to_text(fmt=fmt)
        reparsed = PromptFile.parse(once, fmt=fmt)
        assert reparsed.data["future_field"] == value
        assert reparsed.to_text(fmt=fmt) == PromptFile.parse(
            reparsed.to_text(fmt=fmt), fmt=fmt
        ).to_text(fmt=fmt)


@pytest.mark.parametrize("value", ["a\rb", "a\x85b", "a\u2028b", "a\u2029b"])
@pytest.mark.parametrize("fmt", ["md", "yaml"])
def test_yaml_line_break_scalars_round_trip_exactly(value, fmt):
    """YAML's four normalised line breaks must not corrupt unknown field values."""
    original = PromptFile(
        data={"promptfile": 1, "id": "property/line-breaks", "future_field": value},
        body="body",
    )

    reparsed = PromptFile.parse(original.to_text(fmt=fmt), fmt=fmt)

    assert reparsed.data["future_field"] == value


def test_assay_key_is_emitted_first():
    text = PromptFile.parse(RICH).to_text()
    frontmatter = text.split("---", 2)[1]
    assert frontmatter.lstrip().startswith("promptfile:")


@pytest.mark.parametrize("fmt", ["md", "yaml", "json"])
def test_format_conversion_is_lossless(fmt):
    original = PromptFile.parse(RICH)
    converted = PromptFile.parse(original.to_text(fmt=fmt), fmt=fmt)
    assert converted.data["id"] == original.data["id"]
    assert converted.data["x-vendor-thing"] == original.data["x-vendor-thing"]
    assert converted.messages == original.messages


def test_json_output_is_valid_json():
    payload = json.loads(PromptFile.parse(RICH).to_text(fmt="json"))
    assert payload["promptfile"] == 1
    assert payload["id"] == "t/rich"


def test_yaml_output_is_valid_yaml():
    payload = yaml.safe_load(PromptFile.parse(RICH).to_text(fmt="yaml"))
    assert payload["id"] == "t/rich"


# -- validation ------------------------------------------------------------


def test_rich_file_validates_clean():
    assert PromptFile.parse(RICH).validate() == []


def test_unquoted_timestamp_validates():
    """Regression: PyYAML resolves an unquoted ISO timestamp to a datetime object,
    which used to fail the schema's ``type: string`` check on a perfectly valid file."""
    source = (
        "---\npromptfile: 1\nid: t/ts\nname: TS\ndescription: d\n"
        "provenance:\n  created_at: 2026-07-27T00:00:00Z\n  updated_at: 2026-07-27\n---\nbody"
    )
    assert PromptFile.parse(source).validate() == []


def test_timestamp_objects_survive_round_trip():
    """Normalising for validation must not mutate the stored document."""
    import datetime

    source = "---\npromptfile: 1\nid: t/ts2\nprovenance:\n  created_at: 2026-07-27T00:00:00Z\n---\nb"
    pf = PromptFile.parse(source)
    pf.validate()
    assert isinstance(pf.data["provenance"]["created_at"], datetime.datetime)


def test_non_executable_kinds_are_exempt_from_the_evals_rule():
    fragment = "---\npromptfile: 1\nid: t/frag\nname: F\ndescription: d\nkind: system\nstatus: stable\n---\nx"
    assert not any("eval" in p for p in PromptFile.parse(fragment).validate(strict=True))

    executable = "---\npromptfile: 1\nid: t/exec\nname: E\ndescription: d\nstatus: stable\n---\nx"
    assert any("eval" in p for p in PromptFile.parse(executable).validate(strict=True))


def test_bad_id_pattern_fails_schema():
    errors = PromptFile.parse("---\npromptfile: 1\nid: Not Valid ID\n---\nx").validate()
    assert any("id" in e for e in errors)


def test_strict_lint_flags_stable_prompt_without_evals():
    source = "---\npromptfile: 1\nid: t/s\nname: S\ndescription: d\nstatus: stable\n---\nbody"
    problems = PromptFile.parse(source).validate(strict=True)
    assert any("eval" in p for p in problems)


def test_strict_lint_flags_undeclared_template_variable():
    source = (
        "---\npromptfile: 1\nid: t/u\nname: U\ndescription: d\n"
        "input:\n  schema:\n    type: object\n    properties:\n      known: {type: string}\n"
        "---\nUses {{ known }} and {{ undeclared }}."
    )
    problems = PromptFile.parse(source).validate(strict=True)
    assert any("undeclared" in p for p in problems)


# -- accessors -------------------------------------------------------------


def test_template_variables_scans_messages_and_body():
    assert PromptFile.parse(RICH).template_variables() == {"topic"}
    assert PromptFile.parse(MINIMAL).template_variables() == {"name"}


def test_strict_validation_reports_invalid_template_syntax_instead_of_hiding_it():
    broken = PromptFile.parse(MINIMAL.replace("{{ name }}", "{{ name }"))

    errors = broken.validate(strict=True)

    assert any("engine.template: invalid template" in error for error in errors)


def test_bump_increments_version_and_stamps_provenance():
    pf = PromptFile.parse(RICH)
    assert pf.bump(message="why") == 5
    assert pf.data["provenance"]["updated_at"]
    assert pf.data["provenance"]["message"] == "why"
    assert pf.data["provenance"]["imported_from"] == "dotprompt"  # not clobbered


def test_accessors_expose_model_binding():
    pf = PromptFile.parse(RICH)
    assert pf.model_ref == "echo/json"
    assert pf.fallbacks == ["echo/echo"]
    assert pf.params == {"temperature": 0}
    assert pf.provider_params["anthropic"] == {"thinking": {"type": "enabled"}}
    assert pf.required_capabilities == frozenset({"json_mode"})


# -- discovery -------------------------------------------------------------


def test_discover_finds_all_three_encodings_and_skips_noise(tmp_path):
    (tmp_path / "a.prompt.md").write_text(MINIMAL, encoding="utf-8")
    (tmp_path / "b.prompt.yaml").write_text("promptfile: 1\nid: t/b\n", encoding="utf-8")
    (tmp_path / "c.prompt.json").write_text('{"promptfile":  1, "id": "t/c"}', encoding="utf-8")
    (tmp_path / "not-a-prompt.md").write_text("nope", encoding="utf-8")
    noise = tmp_path / "node_modules"
    noise.mkdir()
    (noise / "d.prompt.md").write_text(MINIMAL, encoding="utf-8")

    found = {p.name for p in discover(tmp_path)}
    assert found == {"a.prompt.md", "b.prompt.yaml", "c.prompt.json"}


def test_discover_prunes_dependency_trees_instead_of_walking_then_filtering(tmp_path, monkeypatch):
    """Regression: filtering node_modules after traversal once made discovery take 30s."""
    import assay_core.promptfile as promptfile_module

    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "real.prompt.md").write_text(MINIMAL, encoding="utf-8")
    ignored = tmp_path / "node_modules" / "package" / "deep"
    ignored.mkdir(parents=True)
    (ignored / "noise.prompt.md").write_text(MINIMAL, encoding="utf-8")
    visited: list[str] = []
    real_walk = promptfile_module.os.walk

    def tracking_walk(root):
        for dirpath, dirnames, filenames in real_walk(root):
            visited.append(str(dirpath))
            yield dirpath, dirnames, filenames

    monkeypatch.setattr(promptfile_module.os, "walk", tracking_walk)

    assert [path.name for path in discover(tmp_path)] == ["real.prompt.md"]
    assert not any("node_modules" in path for path in visited)


def test_save_and_load_round_trip(tmp_path):
    pf = PromptFile.parse(RICH)
    path = pf.save(tmp_path / "sub" / "r.prompt.md")
    assert path.exists()
    assert PromptFile.load(path).data["x-another"] == "plain-string"
