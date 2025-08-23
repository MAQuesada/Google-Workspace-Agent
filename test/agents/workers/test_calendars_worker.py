import json
import re
import pytest

from agents.calendar.worker import google_calendar_worker


def _extract_final_ai_message_content(worker_result):
    """
    Helper: return the content string of the last AIMessage in workers_messages.
    Works with your worker result structure shown in the examples.
    """
    msgs = worker_result.get("workers_messages", [])
    # Pick the last AI message (failsafe: fall back to last)
    for m in reversed(msgs):
        # In langchain, AIMessage often has 'additional_kwargs' with 'refusal' key.
        # But safest is to check type name on the object when available.
        # The returned dict may not carry the class, so we just return the last one.
        # Your examples show the last item is the final assistant answer.
        return m.content
    return ""


def _extract_json_block(text: str):
    """
    Extract a JSON code block from an assistant response like:

    ```json
    { ... }
    ```

    If no fenced block is found, try raw JSON parsing.
    """
    if not isinstance(text, str):
        return None

    # fenced block
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # try raw json
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except Exception:
            pass

    return None


@pytest.mark.asyncio
async def test_agent_handles_greeting_without_tools(
    fake_build, fake_user_service, state_ok
):
    """
    Sanity check: a simple greeting should not require a tool call.
    We just verify the worker returns a final assistant message.
    """
    result = await google_calendar_worker.ainvoke(
        {
            "workers_messages": [
                {"type": "human", "content": "Hi. how you can help me?"}
            ],
            "user_id": state_ok["user_id"],
            "account_name": state_ok["account_name"],
        }
    )

    assert "workers_messages" in result
    last = _extract_final_ai_message_content(result)
    assert isinstance(last, str) and len(last) > 0
    # No strict assertion on JSON format here—your worker greets with free text first.


@pytest.mark.asyncio
async def test_agent_creates_event_success(
    fake_build, fake_user_service, state_ok, fake_store
):
    """
    Ask the agent to create an event 'today in the afternoon'.
    With our calendar fakes (no existing events), the tool 'create_event' will be used
    and we should receive a JSON block with the created event.
    """
    # Ensure no conflicts for the window the agent picks
    fake_store["calendar_list_items"] = []  # find_event returns no conflicts

    result = await google_calendar_worker.ainvoke(
        {
            "workers_messages": [
                {
                    "type": "human",
                    "content": "create an event to take the car to the mechanic today in the afternoon, at any time",
                }
            ],
            "user_id": state_ok["user_id"],
            "account_name": state_ok["account_name"],
        }
    )

    # The worker returns the assistant JSON in the last message as a fenced code block.
    content = _extract_final_ai_message_content(result)
    data = _extract_json_block(content)
    assert data is not None, (
        f"Expected JSON in the final assistant message, got: {content}"
    )

    # Validate JSON schema per your spec
    assert "answer" in data and "events" in data
    assert isinstance(data["events"], list) and len(data["events"]) == 1

    ev = data["events"][0]
    assert ev["title"]  # agent generated title based on prompt
    assert ev["start"] and ev["end"] and ev["event_link"]
    # From your fakes, meet_link is "https://meet.example"
    assert ev.get("meet_link") in (
        None,
        "https://meet.example",
    )  # tolerant to agent formatting


@pytest.mark.asyncio
async def test_agent_reports_conflict_on_create(
    fake_build, fake_user_service, state_ok, fake_store
):
    """
    Preload a conflicting event so create_event detects a conflict.
    The tool returns the conflicting event(s); the agent should surface that in the final JSON.
    """
    # A conflicting event in the afternoon window (adjusted to typical 15:00–16:30 slot)
    fake_store["calendar_list_items"] = [
        {
            "id": "evt_conflict",
            "summary": "Existing",
            "start": {"dateTime": "2025-08-23T15:15:00+02:00"},
            "end": {"dateTime": "2025-08-23T16:15:00+02:00"},
            "htmlLink": "https://example/conflict",
        }
    ]

    result = await google_calendar_worker.ainvoke(
        {
            "workers_messages": [
                {
                    "type": "human",
                    "content": "create an event to take the car to the mechanic today in the afternoon, at any time",
                }
            ],
            "user_id": state_ok["user_id"],
            "account_name": state_ok["account_name"],
        }
    )

    content = _extract_final_ai_message_content(result)
    data = _extract_json_block(content)
    assert data is not None, (
        f"Expected JSON in the final assistant message, got: {content}"
    )
    assert "events" in data

    # When conflict occurs, your tools return the conflicting events via clean_event()
    # Check that at least one event is reported and resembles our preloaded one.
    assert len(data["events"]) >= 1
    titles = [e.get("title") for e in data["events"]]
    assert "Existing" in titles or any("conflict" in (t or "").lower() for t in titles)


@pytest.mark.asyncio
async def test_agent_delete_requires_specificity(
    fake_build, fake_user_service, state_ok, fake_store
):
    """
    If the agent tries to delete an event and multiple candidates exist, it should ask for specificity.
    We simulate the tool response with multiple events and verify the agent surfaces that.
    """
    # Seed two events so delete_event will respond with "Multiple events found."
    fake_store["calendar_list_items"] = [
        {
            "id": "a",
            "summary": "One",
            "start": {"dateTime": "2025-08-24T09:00:00+02:00"},
            "end": {"dateTime": "2025-08-24T10:00:00+02:00"},
        },
        {
            "id": "b",
            "summary": "Two",
            "start": {"dateTime": "2025-08-24T09:00:00+02:00"},
            "end": {"dateTime": "2025-08-24T10:00:00+02:00"},
        },
    ]

    result = await google_calendar_worker.ainvoke(
        {
            "workers_messages": [
                {"type": "human", "content": "delete my meeting tomorrow morning"}
            ],
            "user_id": state_ok["user_id"],
            "account_name": state_ok["account_name"],
        }
    )

    content = _extract_final_ai_message_content(result)
    data = _extract_json_block(content)
    # Some agents respond with a clarifying prompt in "answer" and include candidate events in "events"
    assert data is not None
    assert "answer" in data and "events" in data
    assert isinstance(data["events"], list)
    # Expect that the agent didn't silently delete anything (multiple matches)
    assert len(data["events"]) >= 1
