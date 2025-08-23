import json
import re
import pytest

from agents.contacts.worker import google_contact_worker


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
    result = await google_contact_worker.ainvoke(
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
async def test_agent_search_contacts_success(
    fake_build, fake_user_service, state_ok, fake_store
):
    """
    Ask the agent to search for contacts related to 'alejandro'.
    With our contacts fakes, the tool 'search_tool' will be used
    and we should receive a JSON block with the found contacts.
    """
    # Preload some contacts for the search
    fake_store["people_connections_list"] = [
        {
            "resourceName": "people/123",
            "names": [{"displayName": "alejandro martinez navarra"}],
            "emailAddresses": [
                {"value": "alejo@mail.com"},
                {"value": "alexmartiz@mail.com", "type": "work"},
            ],
            "phoneNumbers": [
                {"value": "123456789", "type": "home"},
                {"value": "222222222", "type": "work"},
            ],
        },
        {
            "resourceName": "people/456",
            "names": [{"displayName": "alejandro manuel quesada"}],
            "emailAddresses": [{"value": "alejom@mail.com"}],
            "phoneNumbers": [],
        },
        {
            "resourceName": "people/789",
            "names": [{"displayName": "Manuel Alejandro"}],
            "emailAddresses": [{"value": "manuelalejandro@gmail.com"}],
            "phoneNumbers": [],
        },
    ]

    # Add some other contacts
    fake_store["people_other_contacts_list"] = [
        {
            "resourceName": "otherContacts/101",
            "names": [],
            "emailAddresses": [{"value": "malejandroquesada@gmail.com"}],
            "phoneNumbers": [],
        },
        {
            "resourceName": "otherContacts/102",
            "names": [],
            "emailAddresses": [{"value": "malejandroquesada@mail.com"}],
            "phoneNumbers": [],
        },
    ]

    result = await google_contact_worker.ainvoke(
        {
            "workers_messages": [
                {
                    "type": "human",
                    "content": "Tell me all my contacts related to 'alejandro'",
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
    assert "answer" in data and "contacts" in data
    assert isinstance(data["contacts"], list) and len(data["contacts"]) >= 1

    # Check that we have contacts with alejandro in the name or email
    contact_names = [c.get("full_name", "").lower() for c in data["contacts"]]
    contact_emails = []
    for c in data["contacts"]:
        for email in c.get("emails", []):
            contact_emails.append(email.get("email", "").lower())

    # Should find contacts with "alejandro" in name or email
    assert any("alejandro" in name for name in contact_names) or any(
        "alejandro" in email for email in contact_emails
    )


@pytest.mark.asyncio
async def test_agent_creates_contact_success(
    fake_build, fake_user_service, state_ok, fake_store
):
    """
    Ask the agent to create a new contact.
    With our contacts fakes (no existing contacts), the tool 'create_tool' will be used
    and we should receive a JSON block with the created contact.
    """
    # Ensure no existing contacts for the new contact
    fake_store["people_connections_list"] = []
    fake_store["people_new_contact_id"] = "people_created_123"

    result = await google_contact_worker.ainvoke(
        {
            "workers_messages": [
                {
                    "type": "human",
                    "content": "create a new contact named Juan Pérez with email juan.perez@example.com and phone 555-1234",
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

    # Validate JSON schema per your spec
    assert "answer" in data and "contacts" in data
    assert isinstance(data["contacts"], list) and len(data["contacts"]) == 1

    contact = data["contacts"][0]
    assert contact["full_name"]  # agent generated name based on prompt
    assert len(contact["emails"]) >= 1
    assert len(contact["phones"]) >= 1


@pytest.mark.asyncio
async def test_agent_reports_duplicate_on_create(
    fake_build, fake_user_service, state_ok, fake_store
):
    """
    Preload an existing contact so create_contact detects a duplicate.
    The tool returns the existing contact; the agent should surface that in the final JSON.
    """
    # An existing contact with the same name
    fake_store["people_connections_list"] = [
        {
            "resourceName": "people/existing",
            "names": [
                {
                    "givenName": "Juan",
                    "familyName": "Pérez",
                    "displayName": "Juan Pérez",
                }
            ],
            "emailAddresses": [{"value": "juan.perez@example.com"}],
            "phoneNumbers": [{"value": "555-1234"}],
        }
    ]

    result = await google_contact_worker.ainvoke(
        {
            "workers_messages": [
                {
                    "type": "human",
                    "content": "create a new contact named Juan Pérez with email juan.perez@example.com",
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
    assert "contacts" in data

    # When duplicate occurs, your tools return the existing contact
    # Check that at least one contact is reported and resembles our preloaded one.
    assert len(data["contacts"]) >= 1
    names = [c.get("full_name") for c in data["contacts"]]
    assert "Juan Pérez" in names


@pytest.mark.asyncio
async def test_agent_delete_requires_specificity(
    fake_build, fake_user_service, state_ok, fake_store
):
    """
    If the agent tries to delete a contact and multiple candidates exist, it should ask for specificity.
    We simulate the tool response with multiple contacts and verify the agent surfaces that.
    """
    # Seed two contacts so delete_contact will respond with "Multiple contacts found."
    fake_store["people_connections_list"] = [
        {
            "resourceName": "people/a",
            "names": [
                {
                    "givenName": "Juan",
                    "familyName": "Pérez",
                    "displayName": "Juan Pérez",
                }
            ],
            "emailAddresses": [{"value": "juan.perez@example.com"}],
            "phoneNumbers": [],
        },
        {
            "resourceName": "people/b",
            "names": [
                {
                    "givenName": "Juan",
                    "familyName": "Carlos",
                    "displayName": "Juan Carlos",
                }
            ],
            "emailAddresses": [{"value": "juan.carlos@example.com"}],
            "phoneNumbers": [],
        },
    ]

    result = await google_contact_worker.ainvoke(
        {
            "workers_messages": [{"type": "human", "content": "delete contact juan"}],
            "user_id": state_ok["user_id"],
            "account_name": state_ok["account_name"],
        }
    )

    content = _extract_final_ai_message_content(result)
    data = _extract_json_block(content)
    # Some agents respond with a clarifying prompt in "answer" and include candidate contacts in "contacts"
    assert data is not None
    assert "answer" in data and "contacts" in data
    assert isinstance(data["contacts"], list)
    # Expect that the agent didn't silently delete anything (multiple matches)
    assert len(data["contacts"]) >= 1


@pytest.mark.asyncio
async def test_agent_updates_contact_success(
    fake_build, fake_user_service, state_ok, fake_store
):
    """
    Ask the agent to update an existing contact.
    With our contacts fakes, the tool 'update_tool' will be used
    and we should receive a JSON block with the updated contact.
    """
    # Preload a contact to update
    fake_store["people_connections_list"] = [
        {
            "resourceName": "people/123",
            "etag": "etag123",
            "names": [
                {
                    "givenName": "Juan",
                    "familyName": "Pérez",
                    "displayName": "Juan Pérez",
                }
            ],
            "emailAddresses": [{"value": "juan.perez@example.com"}],
            "phoneNumbers": [],
        }
    ]

    result = await google_contact_worker.ainvoke(
        {
            "workers_messages": [
                {
                    "type": "human",
                    "content": "update contact Juan Pérez to add phone number 555-9999",
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

    # Validate JSON schema per your spec
    assert "answer" in data and "contacts" in data
    assert isinstance(data["contacts"], list) and len(data["contacts"]) == 1

    contact = data["contacts"][0]
    assert contact["full_name"] == "Juan Pérez"
    assert len(contact["phones"]) >= 1
    # Check that the new phone number was added
    phone_numbers = [p.get("phone") for p in contact["phones"]]
    assert "555-9999" in phone_numbers


@pytest.mark.asyncio
async def test_agent_search_no_results(
    fake_build, fake_user_service, state_ok, fake_store
):
    """
    Test search with no matching contacts.
    The agent should return an empty contacts list with appropriate message.
    """
    # No contacts in the store
    fake_store["people_connections_list"] = []
    fake_store["people_other_contacts_list"] = []

    result = await google_contact_worker.ainvoke(
        {
            "workers_messages": [
                {
                    "type": "human",
                    "content": "find contacts with name 'nonexistent'",
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

    # Should have empty contacts list
    assert "contacts" in data
    assert isinstance(data["contacts"], list)
    assert len(data["contacts"]) == 0
