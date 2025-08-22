
import os
import tempfile

import pytest
import yaml


@pytest.fixture
def sample_config():
    """App-level config with reasoning strategies."""
    return {
        "reasoning_strategies": {
            "step_by_step": "Think through this step by step:",
            "analytical": "Analyze the problem systematically:",
        }
    }


@pytest.fixture
def sample_prompt_data():
    """Full-featured prompt data for building prompts."""
    return {
        "role": "You are a helpful assistant",
        "goal": "Help users with their questions",
        "instruction": "Answer the user's question clearly and concisely",
        "context": "You have access to various resources: {question} and {context}",
        "output_constraints": ["Be accurate", "Be helpful"],
        "style_or_tone": "Professional and friendly",
        "output_format": "Provide a clear answer with examples",
        "examples": ["Example 1: ...", "Example 2: ..."],
        "reasoning_strategy": "step_by_step",
        "input_variables": ["question", "context"],
    }


@pytest.fixture
def temp_config_file(sample_config):
    """Create a temporary app config YAML file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.safe_dump(sample_config, f)
        temp_path = f.name
    try:
        yield temp_path
    finally:
        os.unlink(temp_path)


@pytest.fixture
def temp_prompt_file(sample_prompt_data):
    """Create a temporary prompt YAML file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.safe_dump(sample_prompt_data, f)
        temp_path = f.name
    try:
        yield temp_path
    finally:
        os.unlink(temp_path)

