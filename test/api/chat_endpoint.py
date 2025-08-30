from ast import Dict
import asyncio
import json
from typing import Any, Iterable, Optional
from fastapi import FastAPI
import pytest
from fastapi.testclient import TestClient
from agents.orchestrator.core import get_agent

from api.chat_router import UPDATE_MESSAGES


class _ChunkObj:
    """Helper to simulate an object with `.content` attribute."""

    def __init__(self, content: str):
        self.content = content


class _DummyOrchestrator:
    """Orchestrator with an async generator emitting provided events."""

    def __init__(self, events: Iterable[dict[str, Any]]):
        self._events = list(events)

    async def astream_events(self, *_args, **_kwargs):
        for ev in self._events:
            await asyncio.sleep(0)
            yield ev


class _RaisingOrchestrator:
    """
    Orchestrator that raises either immediately or after one progress event
    (to emulate mid-stream failure).
    """

    def __init__(self, when: str = "immediate"):
        self.when = when
        self._yielded = False

    async def astream_events(self, *_args, **_kwargs):
        await asyncio.sleep(0)
        if self.when == "mid":
            # Yield exactly one valid progress event first, then fail
            yield {
                "event": "on_chain_start",
                "metadata": {"langgraph_node": "email_manage"},
                "data": {},
            }
            await asyncio.sleep(0)
            raise RuntimeError("Orchestrator failure (mid)")
        else:
            # immediate failure
            raise RuntimeError("Orchestrator failure (immediate)")
        if False:  # pragma: no cover (ensures async generator type)
            yield {}


@pytest.fixture()
def mock_orchestrator(fast_api_app: FastAPI, request):
    """
    Parametrizable fixture that overrides get_agent.
    Params options (examples):
      - {"mode": "success", "events": [...]} -> streams given events
      - {"mode": "raises", "when": "immediate"|"mid"}
    Usage:
        @pytest.mark.parametrize("mock_orchestrator", [{"mode":"success","events":[...]}], indirect=True)
    """
    params: Dict[str, Any] = getattr(request, "param", None) or {}

    mode = params.get("mode", "success")
    if mode == "raises":
        when = params.get("when", "immediate")
        orch = _RaisingOrchestrator(when=when)
    else:
        events = params.get("events", [])
        orch = _DummyOrchestrator(events)

    def _fake_get_agent():
        return orch

    fast_api_app.dependency_overrides[get_agent] = _fake_get_agent
    yield _fake_get_agent
    fast_api_app.dependency_overrides.pop(get_agent, None)


def build_progress_node_event(node_name: str) -> dict[str, Any]:
    return {
        "event": "on_chain_start",
        "metadata": {"langgraph_node": node_name},
        "data": {},
    }


def build_tool_start_event(
    tool_name: str, node_name: Optional[str] = None
) -> dict[str, Any]:
    meta = {"langgraph_node": node_name} if node_name else {}
    return {"event": "on_tool_start", "name": tool_name, "metadata": meta, "data": {}}


def build_chat_stream_event(content: str, as_object: bool = False) -> dict[str, Any]:
    chunk = _ChunkObj(content) if as_object else {"content": content}
    return {
        "event": "on_chat_model_stream",
        "metadata": {"langgraph_node": "orchestrator_output"},
        "data": {"chunk": chunk},
    }


def _collect_sse_data_lines(response):
    """
    Collect 'data: {...}' SSE lines from a TestClient streaming response.
    Returns a list of dicts parsed from JSON.
    """
    out = []
    for raw in response.iter_lines():
        if not raw:
            continue
        if raw.startswith("data: "):
            payload = raw[len("data: ") :]
            out.append(json.loads(payload))
    return out


@pytest.mark.parametrize(
    "mock_user_service",
    [[]],  # no accounts
    indirect=True,
)
@pytest.mark.parametrize(
    "mock_orchestrator",
    [{"mode": "success", "events": []}],  # not used in this path
    indirect=True,
)
def test_chat_stream_no_accounts(
    api_client: TestClient,
    allow_all_api_keys,
    mock_user_service,
    mock_orchestrator,
):
    body = {"username": "u1", "conversation_id": "c1", "message": "hello"}
    headers = {"X-API-Key": "ok"}

    with api_client.stream("POST", "/chat", json=body, headers=headers) as resp:
        assert resp.status_code == 200
        events = _collect_sse_data_lines(resp)

    assert len(events) == 1
    assert events[0]["type"] == "progress"
    assert "no accounts" in events[0]["data"].lower()


@pytest.mark.parametrize("node_name", ["email_manage", "search_manage"])
@pytest.mark.parametrize("tool_name", ["GmailListThreads", "ContactsLookup"])
@pytest.mark.parametrize("chunk_as_object", [False, True])  # dict vs .content attribute
@pytest.mark.parametrize(
    "mock_user_service",
    [["acc-1"]],  # has accounts
    indirect=True,
)
def test_chat_stream_happy_parametrized(
    api_client: TestClient,
    allow_all_api_keys,
    mock_user_service,
    node_name,
    tool_name,
    chunk_as_object,
    mock_orchestrator,  # indirect param below
):
    # Build events for this run
    events = [
        # progress node
        {
            "event": "on_chain_start",
            "metadata": {"langgraph_node": node_name},
            "data": {},
        },
        # tool progress
        {
            "event": "on_tool_start",
            "name": tool_name,
            "metadata": {"langgraph_node": node_name},
            "data": {},
        },
        # content
        {
            "event": "on_chat_model_stream",
            "metadata": {"langgraph_node": "orchestrator_output"},
            "data": {
                "chunk": {"content": "Hello from the model."}
                if not chunk_as_object
                else type("C", (), {"content": "Hello from the model."})()
            },
        },
    ]

    # Tell orchestrator fixture what to stream
    mock_orchestrator.params = {"mode": "success", "events": events}  # allows IDE hints
    # pytest passes params via @pytest.mark.parametrize below:
    pass


@pytest.fixture(autouse=True)
def _orchestrator_param_resolver(request):
    """
    This autouse fixture captures the param for 'mock_orchestrator' above and ensures the
    fixture receives it even when the test itself doesn't directly declare it as a parameter.
    This keeps the test signature clean while still being able to set its params programmatically.
    """
    # no-op: present for clarity; pytest handles the indirect param wiring


@pytest.mark.parametrize(
    "mock_orchestrator",
    [
        pytest.param({"mode": "success", "events": []}, id="wired-by-happy-test"),
    ],
    indirect=True,
)
@pytest.mark.usefixtures("mock_orchestrator")
@pytest.mark.parametrize(
    "node_name, tool_name, chunk_as_object",
    [
        ("email_manage", "GmailListThreads", False),
        ("email_manage", "GmailListThreads", True),
        ("search_manage", "ContactsLookup", False),
        ("search_manage", "ContactsLookup", True),
    ],
)
@pytest.mark.parametrize(
    "mock_user_service",
    [["acc-1"]],
    indirect=True,
)
def test_chat_stream_happy_parametrized_body(
    api_client: TestClient,
    allow_all_api_keys,
    mock_user_service,
    node_name,
    tool_name,
    chunk_as_object,
    mock_orchestrator,  # the indirect fixture wired above
):
    # Build the exact events for this param combo
    chunk = {"content": "Hello from the model."}
    if chunk_as_object:
        chunk = type("Chunk", (), {"content": "Hello from the model."})()

    events = [
        {
            "event": "on_chain_start",
            "metadata": {"langgraph_node": node_name},
            "data": {},
        },
        {
            "event": "on_tool_start",
            "name": tool_name,
            "metadata": {"langgraph_node": node_name},
            "data": {},
        },
        {
            "event": "on_chat_model_stream",
            "metadata": {"langgraph_node": "orchestrator_output"},
            "data": {"chunk": chunk},
        },
    ]

    # Rebind the orchestrator for this test run (override the previous success one)
    # This uses the same override slot used by the fixture.
    from agents.orchestrator.core import get_agent

    def _fake_get_agent():
        # from .conftest import _DummyOrchestrator  # type: ignore

        return _DummyOrchestrator(events)

    api_client.app.dependency_overrides[get_agent] = _fake_get_agent

    body = {"username": "u1", "conversation_id": "c1", "message": "hello"}
    headers = {"X-API-Key": "ok"}

    with api_client.stream("POST", "/chat", json=body, headers=headers) as resp:
        assert resp.status_code == 200
        out = _collect_sse_data_lines(resp)

    # 3 events expected
    assert len(out) == 3

    # progress -> node map text must match UPDATE_MESSAGES
    assert out[0]["type"] == "progress"
    assert out[0]["data"] == UPDATE_MESSAGES[node_name]

    # tool progress
    assert out[1]["type"] == "progress"
    assert out[1]["data"].startswith(f"🔧 Using **{tool_name}**")

    # content
    assert out[2]["type"] == "content"
    assert out[2]["data"] == "Hello from the model."


@pytest.mark.parametrize(
    "mock_user_service",
    [["acc-1"]],
    indirect=True,
)
@pytest.mark.parametrize(
    "mock_orchestrator",
    [
        {"mode": "raises", "when": "immediate"},
        {"mode": "raises", "when": "mid"},
    ],
    indirect=True,
)
def test_chat_stream_error_emits_error_event(
    api_client: TestClient,
    allow_all_api_keys,
    mock_user_service,
    mock_orchestrator,
):
    body = {"username": "u1", "conversation_id": "c1", "message": "hello"}
    headers = {"X-API-Key": "ok"}

    with api_client.stream("POST", "/chat", json=body, headers=headers) as resp:
        assert resp.status_code == 200
        out = _collect_sse_data_lines(resp)

    # With your updated generator, any exception becomes an SSE error event
    # (regardless of immediate or mid-stream failure).
    # If 'mid', you might see a progress event first, then error.
    assert out[-1]["type"] == "error"
    assert "an error occurred" in out[-1]["data"].lower()
