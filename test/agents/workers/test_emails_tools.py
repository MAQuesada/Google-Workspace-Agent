import base64
import pytest

from agents.emails.tools import (
    send_email,
    search_emails,
    list_threads,
    fetch_messages_by_thread_id,
    reply_to_thread,
    create_draft,
    list_drafts,
    edit_draft,
    delete_draft,
    send_draft,
)


def test_send_email_happy_path(fake_build, fake_user_service, state_ok, fake_store):
    res = send_email.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        to="dest@x.com",
        subject="Hello",
        body="<b>Hi</b>",
        is_html=True,
        cc=["c1@x.com", "c2@x.com"],
    )
    assert res["details"] == "Email sent successfully."
    assert res["emails"][0]["to"] == "dest@x.com"
    assert res["emails"][0]["subject"] == "Hello"
    assert res["emails"][0]["labels"] == ["SENT"]


def _mk_msg(id_, subject, frm, to, body_text="Body text", unix_ms="1710000000000"):
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


@pytest.mark.parametrize(
    "has_attachment, expected_in_query",
    [
        (False, None),
        (True, "has:attachment"),
    ],
)
def test_search_emails_basic(
    fake_build,
    fake_user_service,
    state_ok,
    fake_store,
    has_attachment,
    expected_in_query,
):
    # messages.list returns two IDs; messages.get returns details for each
    fake_store["gmail_messages_list"] = [{"id": "m1"}, {"id": "m2"}]
    fake_store["gmail_messages_by_id"] = {
        "m1": _mk_msg("m1", "Subj 1", "a@x.com", "me@x.com", "Hello 1"),
        "m2": _mk_msg("m2", "Subj 2", "b@x.com", "me@x.com", "Hello 2"),
    }

    res = search_emails.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        query="from:a@x.com",
        has_attachment=has_attachment,
    )
    assert res["details"].startswith("Found 2 emails")
    assert len(res["emails"]) == 2
    if expected_in_query:
        assert expected_in_query in fake_store["gmail_last_messages_list_params"]["q"]


def test_search_emails_specific_ids(
    fake_build, fake_user_service, state_ok, fake_store
):
    # When specific_message_ids is provided, .list is skipped and only .get is used
    fake_store["gmail_messages_by_id"] = {
        "x1": _mk_msg("x1", "Subj", "c@x.com", "me@x.com"),
    }
    res = search_emails.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        specific_message_ids=["x1"],
    )
    assert res["details"].startswith("Found 1 emails")
    assert res["emails"][0]["id"] == "x1"


def test_list_threads_happy_path(fake_build, fake_user_service, state_ok, fake_store):
    # threads.list returns two threads; threads.get returns details including messages
    fake_store["gmail_threads_list"] = [{"id": "t1"}, {"id": "t2"}]
    fake_store["gmail_threads_by_id"] = {
        "t1": {
            "id": "t1",
            "messages": [
                _mk_msg(
                    "m11",
                    "Th1 msg1",
                    "from1@x.com",
                    "to1@x.com",
                    unix_ms="1710000001000",
                ),
                _mk_msg(
                    "m12",
                    "Th1 msg2",
                    "from2@x.com",
                    "to2@x.com",
                    unix_ms="1710000002000",
                ),
            ],
        },
        "t2": {
            "id": "t2",
            "messages": [
                _mk_msg(
                    "m21",
                    "Th2 msg1",
                    "from3@x.com",
                    "to3@x.com",
                    unix_ms="1710000100000",
                ),
            ],
        },
    }
    res = list_threads.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        query="in:inbox",
    )
    assert res["details"].startswith("Found 2 conversation threads.")
    assert len(res["emails"]) == 2
    # Each entry summarizes the most recent message’s subject
    subjects = {e["subject"] for e in res["emails"]}
    assert "Th1 msg2" in subjects and "Th2 msg1" in subjects


def test_fetch_messages_by_thread_id(
    fake_build, fake_user_service, state_ok, fake_store
):
    fake_store["gmail_threads_by_id"] = {
        "t9": {
            "id": "t9",
            "messages": [
                _mk_msg("z1", "S1", "f@x.com", "me@x.com"),
                _mk_msg("z2", "S2", "f@x.com", "me@x.com"),
            ],
        }
    }
    res = fetch_messages_by_thread_id.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        thread_id="t9",
    )
    assert res["details"] == "Found 2 messages in thread."
    assert [e["id"] for e in res["emails"]] == ["z1", "z2"]


def test_reply_to_thread_sends_to_non_self_sender(
    fake_build, fake_user_service, state_ok, fake_store
):
    fake_store["gmail_profile_email"] = "me@example.com"
    # Oldest message from "other", latest from me — reply should go to "other"
    other_msg = _mk_msg("m1", "Hello", "Other <other@x.com>", "me@example.com")
    my_msg = _mk_msg("m2", "Re: Hello", "Me <me@example.com>", "other@x.com")
    fake_store["gmail_threads_by_id"] = {
        "t1": {"id": "t1", "messages": [other_msg, my_msg]}
    }

    res = reply_to_thread.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        thread_id="t1",
        body="Thanks!",
        is_html=False,
    )
    assert res["details"] == "Reply sent successfully."
    assert res["emails"][0]["to"] == "other@x.com"
    assert res["emails"][0]["subject"].startswith("Re:")


def test_create_draft_success(fake_build, fake_user_service, state_ok, fake_store):
    res = create_draft.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        to="to@x.com",
        subject="Subject X",
        body="Content",
        is_html=False,
        cc=["c@x.com"],
    )
    assert res["details"] == "Draft created successfully."
    assert res["emails"][0]["labels"] == ["DRAFT"]


@pytest.mark.parametrize(
    "specific_ids, expect_empty",
    [
        (["drA", "drB"], False),
        ([], True),  # with no drafts preloaded, list path returns empty
    ],
)
def test_list_drafts_parametrized(
    fake_build, fake_user_service, state_ok, fake_store, specific_ids, expect_empty
):
    if specific_ids:
        # When asking for specific drafts, provide minimal "full" objects:
        fake_store["gmail_drafts_by_id_full"] = {
            did: {
                "id": did,
                "message": {
                    "payload": {
                        "headers": [
                            {"name": "To", "value": "t@x.com"},
                            {"name": "Subject", "value": f"Sub {did}"},
                            {"name": "From", "value": "me@x.com"},
                        ],
                        "parts": [
                            {
                                "mimeType": "text/plain",
                                "body": {
                                    "data": base64.urlsafe_b64encode(b"Body").decode()
                                },
                            }
                        ],
                    },
                    "internalDate": "1710000000000",
                    "labelIds": ["DRAFT"],
                },
            }
            for did in specific_ids
        }

    res = list_drafts.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        specific_draft_ids=specific_ids or None,
    )
    if expect_empty:
        assert res["details"] == "No drafts found matching the query."
        assert res["emails"] == []
    else:
        assert res["details"].startswith("Found")
        assert len(res["emails"]) == len(specific_ids)


def test_edit_draft_updates_subject_and_cc(
    fake_build, fake_user_service, state_ok, fake_store
):
    # _Drafts.get with format='raw' returns a default raw MIME; no need to preload
    res = edit_draft.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        draft_id="dr_raw_1",
        subject="New Subject",
        cc=["c1@x.com", "c2@x.com"],
        body="Updated body",
        is_html=False,
    )
    assert res["details"] == "Draft updated successfully"
    assert res["emails"][0]["subject"] == "New Subject"
    assert res["emails"][0]["cc"] == ["c1@x.com", "c2@x.com"]


def test_delete_draft_deletes_ids(fake_build, fake_user_service, state_ok, fake_store):
    res = delete_draft.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        draft_ids=["d1", "d2"],
    )
    assert res["details"].startswith("Deleted 2 drafts successfully.")
    assert "gmail_drafts_deleted" in fake_store
    assert set(fake_store["gmail_drafts_deleted"]) == {"d1", "d2"}


def test_send_draft_success(fake_build, fake_user_service, state_ok, fake_store):
    # After sending, test will call messages().get() for the sent id.
    msg = {
        "payload": {
            "headers": [
                {"name": "to", "value": "rcpt@x.com"},
                {"name": "from", "value": "me@x.com"},
                {"name": "subject", "value": "Draft Subject"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {
                        "data": base64.urlsafe_b64encode(b"Body from draft").decode()
                    },
                }
            ],
        },
        "labelIds": ["SENT"],
        "threadId": "thr1",
        "internalDate": "1710000000000",
    }
    fake_store["gmail_send_from_draft_id"] = "msg_from_draft_1"
    fake_store["gmail_messages_by_id"] = {"msg_from_draft_1": msg}

    res = send_draft.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        draft_id="dr_to_send",
    )
    assert res["details"] == "Draft sent successfully"
    e = res["emails"][0]
    assert e["id"] == "msg_from_draft_1"
    assert e["to"] == "rcpt@x.com"
    assert e["labels"] == ["SENT"]
