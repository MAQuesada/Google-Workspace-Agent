import builtins
import os
import tempfile

import pytest
import yaml
from langchain_core.prompts import PromptTemplate

from prompts.core import (
    PromptBuilder,
    PromptError,
    YamlLoadError,
)


def test_init_with_valid_config(temp_config_file, sample_config):
    builder = PromptBuilder(temp_config_file)
    assert builder.app_config == sample_config


def test_init_fallback_on_yaml_error_prints_and_empties(monkeypatch, capsys):
    """Single consolidated test for: prints error + app_config={} on load failure."""

    def fake_load_yaml(_):
        raise YamlLoadError("boom")

    monkeypatch.setattr(PromptBuilder, "load_yaml", staticmethod(fake_load_yaml))

    _ = PromptBuilder("whatever.yaml")
    captured = capsys.readouterr()
    assert "Error loading YAML config:" in captured.out


@pytest.mark.parametrize(
    "input, expected",
    [
        ("", ""),
        ("a", "A"),
        ("alpha", "Alpha"),
        ("1alpha", "1alpha"),
        ("World", "World"),
    ],
)
def test_uppercase_first_char(input, expected):
    assert PromptBuilder._uppercase_first_char(input) == expected


@pytest.mark.parametrize(
    "input, expected",
    [
        ("", ""),
        ("A", "a"),
        ("Alpha", "alpha"),
        ("1Alpha", "1Alpha"),
        ("world", "world"),
    ],
)
def test_lowercase_first_char(input, expected):
    assert PromptBuilder._lowercase_first_char(input) == expected


def test_load_yaml_success(temp_config_file, sample_config):
    out = PromptBuilder.load_yaml(temp_config_file)
    assert out == sample_config


def test_load_yaml_file_not_found_raises():
    with pytest.raises(YamlLoadError, match="File not found"):
        PromptBuilder.load_yaml("nope/does_not_exist.yaml")


def test_load_yaml_yaml_error_raises(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("key: [unclosed", encoding="utf-8")
    with pytest.raises(YamlLoadError, match="Error parsing YAML file"):
        PromptBuilder.load_yaml(str(p))


def test_load_yaml_oserror_raises(monkeypatch, tmp_path):
    def boom(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(builtins, "open", boom)
    p = tmp_path / "any.yaml"
    p.write_text("a: 1\n", encoding="utf-8")
    with pytest.raises(YamlLoadError, match="Error reading YAML file"):
        PromptBuilder.load_yaml(str(p))


def test_format_prompt_section_string_with_and_without_lead_in(temp_config_file):
    pb = PromptBuilder(temp_config_file)
    out1 = pb._format_prompt_section("Title:", "hello world")
    assert out1 == "Title:\nHello world"
    out2 = pb._format_prompt_section("", "hello world")
    assert out2 == "Hello world"


@pytest.mark.parametrize(
    "lead_in, items, expected",
    [
        ("Lead:", ["item1", "item2"], "Lead:\n- Item1\n- Item2\n"),
        ("", ["item1", "item2"], "- Item1\n- Item2\n"),
    ],
)
def test_format_prompt_section_list_variants(
    temp_config_file, lead_in, items, expected
):
    pb = PromptBuilder(temp_config_file)
    assert pb._format_prompt_section(lead_in, items) == expected


def test_format_prompt_section_nested_list(temp_config_file):
    pb = PromptBuilder(temp_config_file)
    nested = ["item1", ["nested1", "nested2"], "item3"]
    out = pb._format_prompt_section("Test:", nested)
    assert out == "Test:\n- Item1\n  - Nested1\n  - Nested2\n- Item3\n"


def test_format_prompt_section_deeply_nested(temp_config_file):
    pb = PromptBuilder(temp_config_file)
    nested = ["one", ["two", ["three", "four"]]]
    out = pb._format_prompt_section("Levels:", nested)
    assert out.splitlines() == [
        "Levels:",
        "- One",
        "  - Two",
        "    - Three",
        "    - Four",
    ]


def test_format_prompt_section_empty_string(temp_config_file):
    pb = PromptBuilder(temp_config_file)
    assert pb._format_prompt_section("", "") == ""


# ------------------------------------------------------------------------------
# _build_prompt
# ------------------------------------------------------------------------------


def test_build_prompt_raises_when_instruction_missing(temp_config_file):
    pb = PromptBuilder(temp_config_file)
    with pytest.raises(PromptError, match="Missing required field: 'instruction'"):
        pb._build_prompt({"role": "Assistant"})


def test_build_prompt_minimal(temp_config_file):
    pb = PromptBuilder(temp_config_file)
    prompt, vars_ = pb._build_prompt({"instruction": "Do something"})
    assert "## Your task is as follows:" in prompt
    assert "Do something" in prompt
    assert vars_ == []


def test_build_prompt_includes_sections_and_reasoning(
    temp_config_file, sample_prompt_data
):
    pb = PromptBuilder(temp_config_file)
    prompt, vars_ = pb._build_prompt(sample_prompt_data, input_data="Some input text")
    assert "## ROLE:" in prompt
    assert "## Your goal is to achieve the following outcome:" in prompt
    assert "## Your task is as follows:" in prompt
    assert "## Here's some background that may help you:" in prompt
    assert "## Ensure your response follows these rules:" in prompt
    assert "## Follow these style and tone guidelines:" in prompt
    assert "## Structure your response as follows:" in prompt
    assert "Here are some examples to guide your response:" in prompt
    assert "<<<BEGIN CONTENT>>>" in prompt and "<<<END CONTENT>>>" in prompt
    assert "Think through this step by step:" in prompt  # from sample_config
    assert "Now perform the task as instructed above." in prompt
    assert vars_ == ["question", "context"]


def test_build_prompt_omits_content_block_when_no_input_data(
    temp_config_file, sample_prompt_data
):
    pb = PromptBuilder(temp_config_file)
    prompt, _ = pb._build_prompt(sample_prompt_data, input_data="")
    assert "<<<BEGIN CONTENT>>>" not in prompt
    assert "<<<END CONTENT>>>" not in prompt


def test_build_prompt_no_app_config_skips_reasoning(monkeypatch, sample_prompt_data):
    def fail(_):
        raise YamlLoadError("fail")

    monkeypatch.setattr(PromptBuilder, "load_yaml", staticmethod(fail))
    pb = PromptBuilder("missing.yaml")
    prompt, _ = pb._build_prompt(sample_prompt_data, input_data="")
    assert "Think through this step by step:" not in prompt


@pytest.mark.parametrize(
    "input_vars, expected",
    [
        (None, []),
        ([], []),
        (["x"], ["x"]),
    ],
)
def test_build_prompt_input_variables_handling(temp_config_file, input_vars, expected):
    pb = PromptBuilder(temp_config_file)
    data = {"instruction": "do x", "input_variables": input_vars}
    _, vars_ = pb._build_prompt(data, "")
    assert vars_ == expected


def test_build_prompt_input_variables_not_list_raises(temp_config_file):
    pb = PromptBuilder(temp_config_file)
    data = {"instruction": "do x", "input_variables": "name"}
    with pytest.raises(PromptError, match="Input variables must be a list"):
        pb._build_prompt(data, "")


def test_build_prompt_examples_as_string(temp_config_file):
    pb = PromptBuilder(temp_config_file)
    data = {
        "instruction": "do something",
        "examples": "Single example",
        "input_variables": [],
    }
    prompt, _ = pb._build_prompt(data, "")
    assert "Here are some examples to guide your response:" in prompt
    assert "Single example" in prompt


def test_build_prompt_reasoning_strategy_not_found(temp_config_file):
    pb = PromptBuilder(temp_config_file)
    data = {
        "instruction": "do x",
        "reasoning_strategy": "does_not_exist",
        "input_variables": [],
    }
    prompt, _ = pb._build_prompt(data, "")
    assert "does_not_exist" not in prompt
    assert "Think through this step by step:" not in prompt


def test_prompt_with_empty_sections(temp_config_file):
    pb = PromptBuilder(temp_config_file)
    prompt_data = {
        "instruction": "Do something",
        "role": "",
        "goal": "",
        "context": "",
        "output_constraints": [],
        "style_or_tone": "",
        "output_format": "",
        "examples": [],
    }
    prompt, _ = pb._build_prompt(prompt_data)
    assert "## Your task is as follows:" in prompt
    assert "Do something" in prompt


def test_prompt_with_mixed_example_content_types(temp_config_file):
    pb = PromptBuilder(temp_config_file)
    prompt_data = {
        "instruction": "Do something",
        "examples": [
            "Simple string example",
            ["Nested list example", "Another nested item"],
            "Another simple string",
        ],
    }
    prompt, _ = pb._build_prompt(prompt_data)
    assert "Simple string example" in prompt
    assert "Nested list example" in prompt
    assert "Another nested item" in prompt


def test_build_prompt_reads_yaml_file(temp_prompt_file, temp_config_file):
    builder = PromptBuilder(temp_config_file)
    prompt, input_vars = builder.build_prompt(temp_prompt_file)
    assert "## ROLE:" in prompt
    assert input_vars == ["question", "context"]


def test_build_prompt_reads_yaml_file_with_input_data(
    temp_prompt_file, temp_config_file
):
    builder = PromptBuilder(temp_config_file)
    prompt, _ = builder.build_prompt(temp_prompt_file, "Test input content")
    assert "<<<BEGIN CONTENT>>>" in prompt
    assert "Test input content" in prompt


def test_build_prompt_template_success(temp_prompt_file, temp_config_file):
    builder = PromptBuilder(temp_config_file)
    template = builder.build_prompt_template(temp_prompt_file)
    assert isinstance(template, PromptTemplate)
    assert set(template.input_variables) == {"question", "context"}


def test_build_prompt_template_mismatched_variables(temp_config_file):
    prompt_data = {
        "instruction": "Do something with {question} and {context}",
        "input_variables": ["question", "context", "extra_var"],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.safe_dump(prompt_data, f)
        path = f.name
    try:
        builder = PromptBuilder(temp_config_file)
        with pytest.raises(
            PromptError, match="Input variables in the template do not match"
        ):
            builder.build_prompt_template(path)
    finally:
        os.unlink(path)


def test_build_prompt_template_invalid_template(temp_config_file):
    prompt_data = {
        "instruction": "Do something with {invalid_syntax",
        "input_variables": [],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.safe_dump(prompt_data, f)
        path = f.name
    try:
        builder = PromptBuilder(temp_config_file)
        with pytest.raises(PromptError, match="Error building prompt template"):
            builder.build_prompt_template(path)
    finally:
        os.unlink(path)
