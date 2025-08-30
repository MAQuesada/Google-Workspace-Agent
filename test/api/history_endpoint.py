import json
import pytest
from fastapi.testclient import TestClient

from api.chat_router import extract_user_request
import api.chat_router as chat_module

from langchain_core.messages import HumanMessage, AIMessage


@pytest.mark.parametrize(
    "case, expected",
    [
        pytest.param(
            "### The user's request is:\nHello there!\n\n---",
            "Hello there!",
            id="simple",
        ),
        pytest.param(
            "prefix\n### The user's request is:\nLine 1\nLine 2\n\n---\nsuffix",
            "Line 1\nLine 2",
            id="multiline",
        ),
        pytest.param(
            "### The user's request is:\nMissing terminator only",
            "",  # No terminating \n\n---, so returns ""
            id="missing_terminator",
        ),
        pytest.param("No relevant section at all", "", id="no_match"),
        pytest.param(
            "noise\n\n### The user's request is:\n  Trim me   \n\n---\nmore noise",
            "Trim me",
            id="trimmed",
        ),
    ],
)
def test_extract_user_request_cases(case, expected):
    assert extract_user_request(case) == expected


def _override_user_service(monkeypatch, accounts):
    """Patch api.chat_router.get_user_service to control list_accounts()."""

    class DummyUserService:
        def list_accounts(self, username: str):
            return accounts

    def fake_get_user_service():
        return DummyUserService()

    monkeypatch.setattr(
        chat_module, "get_user_service", fake_get_user_service, raising=True
    )
    return fake_get_user_service


def _override_get_agent_with_messages(monkeypatch, messages):
    """
    Patch api.chat_router.get_agent to return a dummy graph
    whose get_state().values['messages'] is exactly `messages`.
    """

    class DummyState:
        def __init__(self, messages):
            self.values = {"messages": messages}

    class DummyGraph:
        def get_state(self, _config):
            return DummyState(messages)

    def _fake_get_agent():
        return DummyGraph()

    monkeypatch.setattr(chat_module, "get_agent", _fake_get_agent, raising=True)
    return _fake_get_agent


def _collect_response_json(resp):
    assert resp.status_code == 200
    # TestClient returns JSON directly for non-stream responses
    return resp.json()


def test_get_history_no_accounts(
    api_client: TestClient,
    allow_all_api_keys,
    monkeypatch,
):
    _override_user_service(monkeypatch, accounts=[])
    # Orchestrator override not needed; code should early-return []
    params = {"username": "u1", "conversation_id": "c1"}
    headers = {"X-API-Key": "ok"}

    resp = api_client.get("/chat/history", params=params, headers=headers)
    data = _collect_response_json(resp)
    assert data == []


@pytest.mark.parametrize(
    "user_block_text, expected_extracted",
    [
        pytest.param(
            "### The user's request is:\nFind my emails from yesterday\n\n---",
            "Find my emails from yesterday",
            id="user_block_ok",
        ),
        pytest.param(
            "no marker here",
            "",  # extract_user_request returns empty on no match
            id="user_block_missing_marker",
        ),
    ],
)
def test_get_history_with_messages(
    api_client: TestClient,
    allow_all_api_keys,
    monkeypatch,
    user_block_text,
    expected_extracted,
):
    # 1) User has accounts
    _override_user_service(monkeypatch, accounts=["acc-1"])

    # 2) Build mixed message history
    messages = [
        HumanMessage(content=user_block_text),
        AIMessage(content="Sure, I can help with that."),
        HumanMessage(content="### The user's request is:\nAnother ask\n\n---"),
        AIMessage(content="Here is the result."),
    ]

    # 3) Orchestrator returns those messages
    _override_get_agent_with_messages(monkeypatch, messages)

    params = {"username": "u1", "conversation_id": "c1"}
    headers = {"X-API-Key": "ok"}

    resp = api_client.get("/chat/history", params=params, headers=headers)
    data = _collect_response_json(resp)

    # Expected mapping with extraction applied to HumanMessage entries
    # First user entry = expected_extracted (case-dependent),
    # then assistant, then another user (extracted), then assistant.
    assert data[0] == {"role": "user", "content": expected_extracted}
    assert data[1] == {"role": "assistant", "content": "Sure, I can help with that."}
    assert data[2] == {"role": "user", "content": "Another ask"}
    assert data[3] == {"role": "assistant", "content": "Here is the result."}

    # Sanity: length matches input messages
    assert len(data) == 4
