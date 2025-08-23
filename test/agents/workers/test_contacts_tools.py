import pytest

from agents.contacts.tools_google import (
    clean_contacts,
    remove_keys_from_contacts,
    find_contact_by_query,
    delete_contact,
    create_contact,
    update_contact,
    get_contacts,
)
from conftest import FakePeopleService


@pytest.mark.parametrize(
    "contacts, fields, include_source, expected",
    [
        (
            [
                {
                    "names": [{"displayName": "John Doe"}],
                    "emailAddresses": [{"value": "john@example.com", "type": "work"}],
                    "phoneNumbers": [{"value": "+1234567890", "type": "mobile"}],
                    "resourceName": "people/123",
                }
            ],
            [],
            True,
            [
                {
                    "full_name": "John Doe",
                    "emails": [{"email": "john@example.com", "type": "work"}],
                    "phones": [{"phone": "+1234567890", "type": "mobile"}],
                    "source": "My contacts",
                }
            ],
        ),
        (
            [
                {
                    "names": [],
                    "emailAddresses": [],
                    "phoneNumbers": [],
                    "resourceName": "otherContacts/456",
                }
            ],
            [],
            True,
            [
                {
                    "full_name": "No Name",
                    "emails": [],
                    "phones": [],
                    "source": "Other contacts",
                }
            ],
        ),
        (
            [
                {
                    "names": [{"displayName": "Jane Smith"}],
                    "emailAddresses": [{"value": "jane@example.com"}],
                    "phoneNumbers": [{"value": "+0987654321"}],
                    "resourceName": "people/789",
                    "custom_field": "custom_value",
                }
            ],
            ["custom_field"],
            False,
            [
                {
                    "full_name": "Jane Smith",
                    "emails": [{"email": "jane@example.com"}],
                    "phones": [{"phone": "+0987654321"}],
                    "custom_field": "custom_value",
                }
            ],
        ),
    ],
)
def test_clean_contacts_parametrized(contacts, fields, include_source, expected):
    result = clean_contacts(contacts, fields=fields, include_source=include_source)
    assert result == expected


@pytest.mark.parametrize(
    "contacts, keys_to_remove, expected",
    [
        (
            [
                {"name": "John", "email": "john@example.com", "phone": "123"},
                {"name": "Jane", "email": "jane@example.com", "phone": "456"},
            ],
            ["phone"],
            [
                {"name": "John", "email": "john@example.com"},
                {"name": "Jane", "email": "jane@example.com"},
            ],
        ),
        (
            [{"name": "John", "email": "john@example.com"}],
            ["name", "email"],
            [{}],
        ),
        ([], ["key"], []),
    ],
)
def test_remove_keys_from_contacts_parametrized(contacts, keys_to_remove, expected):
    result = remove_keys_from_contacts(contacts, keys_to_remove)
    assert result == expected


def test_find_contact_by_query_name_match(fake_build, fake_user_service, fake_store):
    fake_store["people_connections_list"] = [
        {
            "names": [{"displayName": "John Doe"}],
            "emailAddresses": [{"value": "john@example.com"}],
            "resourceName": "people/123",
        }
    ]
    svc = FakePeopleService(fake_store)
    contacts = find_contact_by_query("john", svc, search_other_contacts=False)
    assert len(contacts) == 1
    assert contacts[0]["full_name"] == "John Doe"


def test_find_contact_by_query_email_match(fake_build, fake_user_service, fake_store):
    fake_store["people_connections_list"] = [
        {
            "names": [{"displayName": "John Doe"}],
            "emailAddresses": [{"value": "john@example.com"}],
            "resourceName": "people/123",
        }
    ]
    svc = FakePeopleService(fake_store)
    contacts = find_contact_by_query(
        "john@example.com", svc, search_other_contacts=False
    )
    assert len(contacts) == 1
    assert contacts[0]["emails"][0]["email"] == "john@example.com"


def test_find_contact_by_query_with_other_contacts(
    fake_build, fake_user_service, fake_store
):
    fake_store["people_connections_list"] = [
        {
            "names": [{"displayName": "John Doe"}],
            "emailAddresses": [{"value": "john@example.com"}],
            "resourceName": "people/123",
        }
    ]
    fake_store["people_other_contacts_list"] = [
        {
            "names": [{"displayName": "Jane Smith"}],
            "emailAddresses": [{"value": "jane@example.com"}],
            "resourceName": "otherContacts/456",
        }
    ]
    svc = FakePeopleService(fake_store)
    contacts = find_contact_by_query("jane", svc, search_other_contacts=True)
    assert len(contacts) == 1
    assert contacts[0]["full_name"] == "Jane Smith"
    assert contacts[0]["source"] == "Other contacts"


def test_delete_contact_success(fake_build, fake_user_service, state_ok, fake_store):
    fake_store["people_connections_list"] = [
        {
            "names": [{"displayName": "John Doe"}],
            "emailAddresses": [{"value": "john@example.com"}],
            "resourceName": "people/123",
        }
    ]
    res = delete_contact.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        query="John Doe",
    )
    assert "deleted" in res["details"]
    assert "people/123" in fake_store.get("people_contacts_deleted", [])


def test_delete_contact_no_match(fake_build, fake_user_service, state_ok, fake_store):
    fake_store["people_connections_list"] = []
    res = delete_contact.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        query="Nonexistent",
    )
    assert "no contacts that match" in res["details"]
    assert res["contacts"] == []


def test_delete_contact_multiple_matches(
    fake_build, fake_user_service, state_ok, fake_store
):
    fake_store["people_connections_list"] = [
        {
            "names": [{"displayName": "John Doe"}],
            "emailAddresses": [{"value": "john@example.com"}],
            "resourceName": "people/123",
        },
        {
            "names": [{"displayName": "John Smith"}],
            "emailAddresses": [{"value": "john.smith@example.com"}],
            "resourceName": "people/456",
        },
    ]
    res = delete_contact.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        query="John",
    )
    assert "multiple contacts found" in res["details"]
    assert len(res["contacts"]) == 2


def test_delete_contact_no_account(monkeypatch, fake_build, state_ok):
    class FakeUserServiceNoAcc:
        def get_account(self, *_):
            return None

    def _get_user_service():
        return FakeUserServiceNoAcc()

    monkeypatch.setattr(
        "agents.contacts.tools_google.get_user_service", _get_user_service
    )

    res = delete_contact.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        query="John",
    )
    assert "Please authenticate with Google first" in res["details"]


def test_create_contact_success(fake_build, fake_user_service, state_ok, fake_store):
    fake_store["people_connections_list"] = []
    fake_store["people_new_contact_id"] = "people_new_123"
    res = create_contact.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        given_name="John",
        family_name="Doe",
        emails=["john@example.com"],
        phones=["+1234567890"],
    )
    assert "created" in res["detail"]
    assert len(res["contacts"]) == 1
    assert (
        fake_store["people_last_create_contact_body"]["names"][0]["givenName"] == "John"
    )
    assert (
        fake_store["people_last_create_contact_body"]["names"][0]["familyName"] == "Doe"
    )


def test_create_contact_already_exists(
    fake_build, fake_user_service, state_ok, fake_store
):
    fake_store["people_connections_list"] = [
        {
            "names": [{"displayName": "John Doe"}],
            "emailAddresses": [{"value": "john@example.com"}],
            "resourceName": "people/123",
        }
    ]
    res = create_contact.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        given_name="John",
        family_name="Doe",
        emails=["john@example.com"],
    )
    assert "already exists" in res["detail"]
    assert len(res["contacts"]) == 1


def test_create_contact_no_account(monkeypatch, fake_build, state_ok):
    class FakeUserServiceNoAcc:
        def get_account(self, *_):
            return None

    def _get_user_service():
        return FakeUserServiceNoAcc()

    monkeypatch.setattr(
        "agents.contacts.tools_google.get_user_service", _get_user_service
    )

    res = create_contact.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        given_name="John",
        family_name="Doe",
    )
    assert "Please authenticate with Google first" in res["detail"]


def test_update_contact_success(fake_build, fake_user_service, state_ok, fake_store):
    fake_store["people_connections_list"] = [
        {
            "names": [{"displayName": "John Doe"}],
            "emailAddresses": [{"value": "john@example.com"}],
            "phoneNumbers": [{"value": "+1234567890"}],
            "resourceName": "people/123",
            "etag": "etag123",
        }
    ]
    res = update_contact.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        query="John Doe",
        new_given_name="Jane",
        new_emails=["jane@example.com"],
    )
    assert "updated successfully" in res["details"]
    assert (
        fake_store["people_last_update_contact"]["updatePersonFields"]
        == "names,emailAddresses,phoneNumbers"
    )


def test_update_contact_no_fields_provided(fake_build, fake_user_service, state_ok):
    res = update_contact.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        query="John Doe",
    )
    assert "Please provide at least one field to update" in res["details"]


def test_update_contact_no_match(fake_build, fake_user_service, state_ok, fake_store):
    fake_store["people_connections_list"] = []
    res = update_contact.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        query="Nonexistent",
        new_given_name="Jane",
    )
    assert "No contact found matching" in res["details"]


def test_update_contact_multiple_matches(
    fake_build, fake_user_service, state_ok, fake_store
):
    fake_store["people_connections_list"] = [
        {
            "names": [{"displayName": "John Doe"}],
            "emailAddresses": [{"value": "john@example.com"}],
            "resourceName": "people/123",
            "etag": "etag123",
        },
        {
            "names": [{"displayName": "John Smith"}],
            "emailAddresses": [{"value": "john.smith@example.com"}],
            "resourceName": "people/456",
            "etag": "etag456",
        },
    ]
    res = update_contact.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        query="John",
        new_given_name="Jane",
    )
    assert "Multiple contacts found" in res["details"]
    assert len(res["contacts"]) == 2


def test_get_contacts_success(fake_build, fake_user_service, state_ok, fake_store):
    fake_store["people_connections_list"] = [
        {
            "names": [{"displayName": "John Doe"}],
            "emailAddresses": [{"value": "john@example.com"}],
            "resourceName": "people/123",
        }
    ]
    fake_store["people_other_contacts_list"] = [
        {
            "names": [{"displayName": "Jane Smith"}],
            "emailAddresses": [{"value": "jane@example.com"}],
            "resourceName": "otherContacts/456",
        }
    ]
    res = get_contacts.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        query="John",
    )
    assert "Contacts found that match" in res["detail"]
    assert len(res["contacts"]) == 1
    assert res["contacts"][0]["full_name"] == "John Doe"


def test_get_contacts_no_match(fake_build, fake_user_service, state_ok, fake_store):
    fake_store["people_connections_list"] = []
    fake_store["people_other_contacts_list"] = []
    res = get_contacts.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        query="Nonexistent",
    )
    assert "No contacts found matching" in res["detail"]
    assert res["contacts"] == []


def test_get_contacts_no_account(monkeypatch, fake_build, state_ok):
    class FakeUserServiceNoAcc:
        def get_account(self, *_):
            return None

    def _get_user_service():
        return FakeUserServiceNoAcc()

    monkeypatch.setattr(
        "agents.contacts.tools_google.get_user_service", _get_user_service
    )

    res = get_contacts.__wrapped__(
        tool_call_id="t1",
        state=state_ok,
        query="John",
    )
    assert "Please authenticate with Google first" in res["detail"]


def test_limit_calls_wrapper_smoke(fake_build, fake_user_service, state_ok):
    cmd = get_contacts(
        tool_call_id="tc_1",
        state={**state_ok, "num_calls": []},
        query="John",
    )
    assert hasattr(cmd, "update")
    upd = cmd.update
    assert upd["num_calls"] == ["get_contacts"]
    assert "workers_messages" in upd and len(upd["workers_messages"]) == 1
    assert upd["workers_messages"][0] is not None


def test_limit_calls_rejects_when_over_quota(fake_build, fake_user_service):
    cmd = get_contacts(
        tool_call_id="tc_2",
        state={"user_id": "u1", "account_name": "acc1", "num_calls": list("x" * 11)},
        query="John",
    )
    upd = cmd.update
    assert upd["num_calls"] == ["get_contacts"]
    assert "workers_messages" in upd and len(upd["workers_messages"]) == 1
