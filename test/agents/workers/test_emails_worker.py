import json
import re
import base64
import pytest

from agents.emails.worker import google_email_worker


def _extract_final_ai_message_content(worker_result):
    """
    Return the content string of the last AI message in workers_messages.
    Falls back to returning the last message's content.
    """
    msgs = worker_result.get("workers_messages", [])
    if not msgs:
        return ""
    # In your examples, the last item is the final assistant (AI) message.
    return msgs[-1].content


def _extract_json_block(text: str):
    """
    Extract a JSON code block from a message like:

    ```json
    { ... }
    ```

    If no fenced block is found, try raw JSON parsing.
    """
    if not isinstance(text, str):
        return None

    m = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except Exception:
            pass
    return None


def _mk_msg(id_, subject, frm, to, body_text="Body text", unix_ms="1710000000000"):
    """
    Build a minimal Gmail message payload compatible with tools.search_emails()
    and reply_to_thread() logic (capitalized headers).
    """
    payload = {
        "headers": [
            {"name": "Subject", "value": subject},
            {"name": "From", "value": frm},
            {"name": "To", "value": to},
        ],
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {"data": base64.urlsafe_b64encode(body_text.encode()).decode()},
            }
        ],
    }
    return {
        "id": id_,
        "threadId": f"th_{id_}",
        "payload": payload,
        "labelIds": ["INBOX"],
        "internalDate": unix_ms,
    }


@pytest.mark.asyncio
async def test_email_agent_handles_greeting_without_tools(
    fake_build, fake_user_service, state_ok
):
    """
    Sanity: Simple greeting should not require a tool call.
    Just verify we get a final assistant message back.
    """
    result = await google_email_worker.ainvoke(
        {
            "workers_messages": [
                {"type": "human", "content": "hello. How you can assist me?"}
            ],
            "user_id": state_ok["user_id"],
            "account_name": state_ok["account_name"],
        }
    )

    content = _extract_final_ai_message_content(result)
    assert isinstance(content, str) and len(content) > 0


@pytest.mark.asyncio
async def test_email_agent_sends_email_success(
    fake_build, fake_user_service, state_ok, fake_store
):
    """
    Ask the agent to send an email. Our fake Gmail 'send' returns a SENT id.
    Validate the final JSON shape and a few key fields.
    """
    # Optional: ensure a stable id from fake send
    fake_store["gmail_send_id"] = "msg_sent_123"

    result = await google_email_worker.ainvoke(
        {
            "workers_messages": [
                {
                    "type": "human",
                    "content": (
                        "Send an email to aless0310@gmail.com and manuel@gmail.com "
                        "inviting them to join a new business project with AI"
                    ),
                }
            ],
            "user_id": state_ok["user_id"],
            "account_name": state_ok["account_name"],
        }
    )

    content = _extract_final_ai_message_content(result)
    data = _extract_json_block(content)
    assert data is not None, f"Expected JSON in assistant message, got: {content}"
    assert "answer" in data and "emails" in data
    assert isinstance(data["emails"], list) and len(data["emails"]) == 1

    email_item = data["emails"][0]
    assert email_item.get("id") == "msg_sent_123" or email_item.get("id")
    assert "to" in email_item
    assert "subject" in email_item
    assert "labels" in email_item and "SENT" in email_item["labels"]


@pytest.mark.asyncio
async def test_email_agent_search_emails_basic(
    fake_build, fake_user_service, state_ok, fake_store
):
    """
    Seed two messages; ask the agent to find emails about 'Project X'.
    The agent should call search_emails and return up to MAX_NUM_DISPLAY_ITEMS (10).
    """
    # Search returns a list of message ids first:
    fake_store["gmail_messages_list"] = [{"id": "m1"}, {"id": "m2"}]

    # Full messages fetched by id:
    fake_store["gmail_messages_by_id"] = {
        "m1": _mk_msg(
            "m1",
            "Project X kickoff",
            "pm@corp.com",
            "me@example.com",
            "Agenda and notes about Project X",
            "1710000000000",
        ),
        "m2": _mk_msg(
            "m2",
            "Re: Project X",
            "me@example.com",
            "team@corp.com",
            "Follow-up on Project X milestones",
            "1710001000000",
        ),
    }

    result = await google_email_worker.ainvoke(
        {
            "workers_messages": [
                {"type": "human", "content": "Find emails about Project X"}
            ],
            "user_id": state_ok["user_id"],
            "account_name": state_ok["account_name"],
        }
    )

    content = _extract_final_ai_message_content(result)
    data = _extract_json_block(content)
    assert data is not None
    assert "emails" in data
    assert len(data["emails"]) >= 1
    subjects = [e.get("subject", "").lower() for e in data["emails"]]
    assert any("project x" in s for s in subjects)


@pytest.mark.asyncio
async def test_email_agent_reply_to_thread_success(
    fake_build, fake_user_service, state_ok, fake_store
):
    """
    Provide an explicit thread_id and messages in the thread:
    oldest from 'other', newest from 'me' — reply should target 'other'.
    """
    fake_store["gmail_profile_email"] = "me@example.com"

    other_msg = _mk_msg("m1", "Hello", "Other <other@x.com>", "me@example.com")
    my_msg = _mk_msg("m2", "Re: Hello", "Me <me@example.com>", "other@x.com")

    fake_store["gmail_threads_by_id"] = {
        "t1": {"id": "t1", "messages": [other_msg, my_msg]}
    }

    # Make send() return a stable id (optional)
    fake_store["gmail_send_id"] = "reply_msg_42"

    result = await google_email_worker.ainvoke(
        {
            "workers_messages": [
                {
                    "type": "human",
                    "content": "Reply to thread t1 with: Thanks for the update!",
                }
            ],
            "user_id": state_ok["user_id"],
            "account_name": state_ok["account_name"],
        }
    )

    content = _extract_final_ai_message_content(result)
    data = _extract_json_block(content)
    assert data is not None
    assert "answer" in data and "emails" in data and len(data["emails"]) >= 1

    reply_item = data["emails"][0]
    # The tool sets 'to' to the non-self sender (other@x.com)
    assert reply_item.get("to") in ("other@x.com", "Other <other@x.com>")
    assert reply_item.get("id") == "reply_msg_42" or reply_item.get("id")
    # Subject should start with "Re:" (agent/tool behavior)
    assert reply_item.get("subject", "").lower().startswith("re:")
