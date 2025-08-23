import base64
import pytest

from agents.calendar.tool_google import (
    get_event_id,
    clean_event,
    find_event,
    get_events,
    find_free_slots,
    delete_event,
    update_event,
    create_event,
)
from conftest import FakeCalendarService


@pytest.mark.parametrize(
    "raw_event_id, calendar_id",
    [
        ("abc123", "foo@bar.com"),
        ("ev_42", "primary"),
        ("my-id", "someone@domain.tld"),
    ],
)
def test_get_event_id_from_url(raw_event_id, calendar_id):
    raw = f"{raw_event_id} {calendar_id}"
    eid = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    url = f"https://www.google.com/calendar/event?eid={eid}"
    assert get_event_id(url) == raw_event_id


@pytest.mark.parametrize("direct_id", ["plain_event_id", "evt_1", "XYZ"])
def test_get_event_id_direct_id(direct_id):
    assert get_event_id(direct_id) == direct_id


@pytest.mark.parametrize(
    "item, expected",
    [
        (
            {
                "summary": "Title",
                "start": {"dateTime": "2025-01-01T10:00:00+00:00"},
                "end": {"dateTime": "2025-01-01T11:00:00+00:00"},
                "htmlLink": "https://example",
                "attendees": [{"email": "a@b.com"}],
                "hangoutLink": "https://meet",
                "description": "desc",
            },
            {
                "title": "Title",
                "start": "2025-01-01T10:00:00+00:00",
                "end": "2025-01-01T11:00:00+00:00",
                "event_link": "https://example",
                "attendees": [{"email": "a@b.com"}],
                "meet_link": "https://meet",
                "description": "desc",
            },
        ),
        (
            {
                "summary": "AllDay",
                "start": {"date": "2025-03-10"},
                "end": {"date": "2025-03-11"},
                "htmlLink": "https://example",
            },
            {
                "title": "AllDay",
                "start": "2025-03-10",
                "end": "2025-03-11",
                "event_link": "https://example",
                "attendees": [],
                "meet_link": None,
                "description": None,
            },
        ),
    ],
)
def test_clean_event_parametrized(item, expected):
    assert clean_event([item], fields=["description"]) == [expected]


def test_find_event_lists_items(fake_build, fake_user_service, fake_store):
    fake_store["calendar_list_items"] = [{"id": "e1", "summary": "Standup"}]
    svc = FakeCalendarService(fake_store)
    items = find_event(
        svc,
        query="standup",
        start_date="2025-08-20T00:00:00+02:00",
        end_date="2025-08-21T00:00:00+02:00",
        timezone="Europe/Paris",
    )
    assert items == [{"id": "e1", "summary": "Standup"}]
    assert fake_store["calendar_last_list_kwargs"]["q"] == "standup"


def test_get_events_happy_path(fake_build, fake_user_service, state_ok, fake_store):
    fake_store["calendar_list_items"] = [
        {
            "id": "e1",
            "summary": "Demo",
            "start": {"dateTime": "2025-08-22T09:00:00+02:00"},
            "end": {"dateTime": "2025-08-22T09:30:00+02:00"},
            "htmlLink": "https://example",
            "hangoutLink": "https://meet",
            "description": "d1",
        }
    ]
    res = get_events.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        query="Demo",
        start_date="2025-08-22T00:00:00+02:00",
        end_date="2025-08-23T00:00:00+02:00",
        timezone="Europe/Paris",
    )
    assert res["details"] == "Events found successfully."
    assert res["events"][0]["title"] == "Demo"
    assert res["events"][0]["description"] == "d1"


def test_get_events_requires_params(fake_build, fake_user_service, state_ok):
    res = get_events.__wrapped__(tool_call_id="t1", state=state_ok)
    assert "Please provide the `query`" in res["details"]


def test_get_events_no_account(monkeypatch, fake_build, state_ok):
    class FakeUserServiceNoAcc:
        def get_account(self, *_):
            return None

    def _get_user_service():
        return FakeUserServiceNoAcc()

    monkeypatch.setattr(
        "agents.calendar.tool_google.get_user_service", _get_user_service
    )

    res = get_events.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        query="x",
        start_date="2025-01-01T00:00:00+00:00",
        end_date="2025-01-02T00:00:00+00:00",
    )
    assert "Please authenticate with Google first" in res["details"]


@pytest.mark.parametrize(
    "busy, expected_slots",
    [
        (
            [
                {
                    "start": "2025-01-01T09:00:00+00:00",
                    "end": "2025-01-01T10:00:00+00:00",
                }
            ],
            [
                ("2025-01-01T08:00", "2025-01-01T09:00"),
                ("2025-01-01T10:00", "2025-01-01T12:00"),
            ],
        ),
        ([], [("2025-01-01T08:00", "2025-01-01T12:00")]),
    ],
)
def test_find_free_slots_parametrized(
    fake_build, fake_user_service, state_ok, fake_store, busy, expected_slots
):
    fake_store["calendar_busy"] = busy
    res = find_free_slots.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        start_date="2025-01-01T08:00:00+00:00",
        end_date="2025-01-01T12:00:00+00:00",
        timezone="UTC",
        min_duration=30,
    )
    assert res["details"] == "Free slots found."
    got = [(slot["start"][:16], slot["end"][:16]) for slot in res["free_slots"]]
    assert got == expected_slots


def test_delete_event_by_id(fake_build, fake_user_service, state_ok, fake_store):
    res = delete_event.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        event_id_or_event_link="evt_123",
    )
    assert "deleted successfully" in res["details"]
    assert "evt_123" in fake_store.get("calendar_deleted_ids", [])


@pytest.mark.parametrize(
    "items, expected_msg, expected_deleted_count",
    [
        (
            [
                {
                    "id": "e1",
                    "summary": "One",
                    "start": {"dateTime": "2025-08-22T10:00:00+02:00"},
                    "end": {"dateTime": "2025-08-22T10:30:00+02:00"},
                    "htmlLink": "https://example",
                }
            ],
            "Event deleted successfully.",
            1,
        ),
        ([{"id": "a"}, {"id": "b"}], "Multiple events found.", 0),
    ],
)
def test_delete_event_by_query_parametrized(
    fake_build,
    fake_user_service,
    state_ok,
    fake_store,
    items,
    expected_msg,
    expected_deleted_count,
):
    fake_store["calendar_list_items"] = items
    res = delete_event.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        query="q",
        start_date="2025-08-22T00:00:00+02:00",
        end_date="2025-08-23T00:00:00+02:00",
    )
    assert expected_msg in res["details"]
    assert len(fake_store.get("calendar_deleted_ids", [])) == expected_deleted_count


def test_update_event_change_title_and_duration_no_conflict(
    fake_build, fake_user_service, state_ok, fake_store
):
    fake_store["calendar_get_event_by_id"] = {
        "evt_1": {
            "id": "evt_1",
            "summary": "Old",
            "start": {"dateTime": "2025-08-22T09:00:00+02:00"},
            "end": {"dateTime": "2025-08-22T09:30:00+02:00"},
            "attendees": [],
        }
    }
    fake_store["calendar_list_items"] = []  # no conflicts

    res = update_event.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        event_id_or_event_link="evt_1",
        title="New Title",
        event_duration_hour=1,
        event_duration_minutes=0,
        ignore_conflicts=False,
    )
    assert res["details"] == "Event updated successfully."
    ev = res["events"][0]
    assert ev["title"] == "New Title"
    assert ev["start"].startswith("2025-08-22T09:00")
    assert ev["end"].startswith("2025-08-22T10:00")


def test_update_event_conflict_detected(
    fake_build, fake_user_service, state_ok, fake_store
):
    fake_store["calendar_get_event_by_id"] = {
        "evt_2": {
            "id": "evt_2",
            "summary": "Keep",
            "start": {"dateTime": "2025-08-22T10:00:00+02:00"},
            "end": {"dateTime": "2025-08-22T10:30:00+02:00"},
        }
    }
    fake_store["calendar_list_items"] = [
        {
            "id": "evt_other",
            "summary": "Conflict",
            "start": {"dateTime": "2025-08-22T10:15:00+02:00"},
            "end": {"dateTime": "2025-08-22T11:00:00+02:00"},
            "htmlLink": "https://example",
        }
    ]

    res = update_event.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        event_id_or_event_link="evt_2",
        start_datetime="2025-08-22T10:00:00+02:00",
        event_duration_minutes=60,
        ignore_conflicts=False,
    )
    assert "cannot be updated due to conflicts" in res["details"]
    assert res["events"][0]["title"] == "Conflict"


@pytest.mark.parametrize(
    "list_items, expect_conflict",
    [
        ([], False),
        (
            [
                {
                    "id": "evt_existing",
                    "summary": "Existing",
                    "start": {"dateTime": "2025-08-22T10:00:00+02:00"},
                    "end": {"dateTime": "2025-08-22T11:00:00+02:00"},
                    "htmlLink": "https://example",
                }
            ],
            True,
        ),
    ],
)
def test_create_event_conflict_and_success(
    fake_build, fake_user_service, state_ok, fake_store, list_items, expect_conflict
):
    fake_store["calendar_list_items"] = list_items
    res = create_event.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        start_datetime="2025-08-22T10:15:00+02:00",
        title="New Meeting",
        event_duration_minutes=30,
        ignore_conflicts=False,
        description="desc",
    )
    if expect_conflict:
        assert "cannot be created due to conflicts" in res["details"]
        assert res["events"][0]["title"] == "Existing"
    else:
        assert res["details"] == "Event created successfully."
        assert res["events"][0]["title"] == "New Meeting"
        assert res["events"][0]["description"] == "desc"


def test_limit_calls_wrapper_smoke(fake_build, fake_user_service, state_ok):
    cmd = get_events(
        tool_call_id="tc_1",
        state={**state_ok, "num_calls": []},
        query="x",
        start_date="2025-01-01T00:00:00+00:00",
        end_date="2025-01-02T00:00:00+00:00",
    )
    assert hasattr(cmd, "update")
    upd = cmd.update
    assert upd["num_calls"] == ["get_events"]
    assert "workers_messages" in upd and len(upd["workers_messages"]) == 1
    assert upd["workers_messages"][0] is not None


def test_limit_calls_rejects_when_over_quota(fake_build, fake_user_service):
    cmd = get_events(
        tool_call_id="tc_2",
        state={"user_id": "u1", "account_name": "acc1", "num_calls": list("x" * 11)},
        query="x",
        start_date="2025-01-01T00:00:00+00:00",
        end_date="2025-01-02T00:00:00+00:00",
    )
    upd = cmd.update
    assert upd["num_calls"] == ["get_events"]
    assert "workers_messages" in upd and len(upd["workers_messages"]) == 1
