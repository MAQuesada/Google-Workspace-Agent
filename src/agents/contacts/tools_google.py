from typing import Annotated, List, Optional
from langgraph.prebuilt import InjectedState
from langchain_core.tools import StructuredTool
from googleapiclient.discovery import build
from agents.contacts.schemas import (
    DeleteSchema,
    CreateSchema,
    UpdateSchema,
    SearchSchema,
)
from agents.utils import limit_calls
from langchain_core.tools.base import InjectedToolCallId

from google_service.core import get_user_service
from utils.config import get_config

CONTACT_FIELDS = "names,emailAddresses,phoneNumbers"
PAGE_ZISE = 1000  # 1000 is the maximum page size for the Google People API
MAX_NUM_DISPLAY_ITEMS = get_config().MAX_NUM_DISPLAY_ITEMS
contacts_toolset = []


def get_all_contacts(service):
    """Retrieve all contacts from the user's Google account."""
    all_contacts = []
    next_page_token = None

    while True:
        response = (
            service.people()
            .connections()
            .list(
                resourceName="people/me",
                pageSize=PAGE_ZISE,
                pageToken=next_page_token,
                personFields=CONTACT_FIELDS,
            )
            .execute()
        )

        connections = response.get("connections", [])
        all_contacts.extend(connections)

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break
    return all_contacts


def get_other_contacts(service):
    """Retrieve all other contacts from the user's Google account.

    Google People API only provides for Other Contacts:
        - names
        - emailAddresses
    """
    other_contacts = []
    next_page_token = None

    while True:
        response = (
            service.otherContacts()
            .list(
                pageSize=PAGE_ZISE, pageToken=next_page_token, readMask=CONTACT_FIELDS
            )
            .execute()
        )

        connections = response.get("otherContacts", [])
        other_contacts.extend(connections)

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    return other_contacts


def clean_contacts(contacts, fields=[], include_source=True):
    """
    Clean and format a list of contacts.

    Each contact will include:
    - full_name: the person's full name, or 'No Name'
    - emails: a list of dicts with 'email' and 'type' (or None)
    - phones: a list of dicts with 'phone' and 'type' (or None)
    - source: 'My contacts' or 'Other contacts' (optional, based on resourceName)
    - additional fields passed via the 'fields' parameter (if present)
    """
    cleaned_contacts = []

    for person in contacts:
        # Names
        names = person.get("names", [])
        full_name = names[0].get("displayName") if names else "No Name"

        # Emails
        email_entries = []
        for email in person.get("emailAddresses", []):
            email_dict = {
                "email": email.get("value"),
            }
            if "type" in email:
                email_dict["type"] = email.get("type")
            email_entries.append(email_dict)

        # Phones
        phone_entries = []
        for phone in person.get("phoneNumbers", []):
            phone_dict = {
                "phone": phone.get("value"),
            }
            if "type" in phone:
                phone_dict["type"] = phone.get("type")
            phone_entries.append(phone_dict)

        person_dict = {
            "full_name": full_name,
            "emails": email_entries,
            "phones": phone_entries,
        }

        if include_source:
            resource_name = person.get("resourceName", "")
            if resource_name.startswith("people/"):
                person_dict["source"] = "My contacts"
            elif resource_name.startswith("otherContacts/"):
                person_dict["source"] = "Other contacts"
            else:
                person_dict["source"] = "Unknown"

        # Include any additional fields specified
        for field in fields:
            person_dict[field] = person.get(field, f"No {field}")

        cleaned_contacts.append(person_dict)

    return cleaned_contacts


def remove_keys_from_contacts(contacts: list, keys_to_remove: list) -> list:
    """
    Remove specified keys from each contact dictionary.

    Args:
        contacts (list): List of contact dictionaries.
        keys_to_remove (list): List of keys to remove from each contact.

    Returns:
        list: A new list of contacts with the specified keys removed.
    """
    cleaned = []

    for contact in contacts:
        cleaned_contact = {k: v for k, v in contact.items() if k not in keys_to_remove}
        cleaned.append(cleaned_contact)

    return cleaned


def find_contact_by_query(
    search_name: str,
    contact_service,
    search_other_contacts: bool = False,
    field_to_keep: list = [],
) -> list:
    """
    Search for a contact by name or email in the user's contacts (and optionally in other contacts).

    Args:
        search_name (str): The string to search for (in name or email).
        contact_service: The authenticated Google People API service.
        search_other_contacts (bool): Whether to search in 'Other contacts' as well.

    Returns:
        List of cleaned contact dicts that match the search.
    """
    search_lower = search_name.lower()

    # Fetch and clean my contacts
    my_contacts_raw = get_all_contacts(contact_service)
    my_contacts_clean = clean_contacts(
        my_contacts_raw, include_source=False, fields=field_to_keep
    )

    matched_contacts = []

    for contact in my_contacts_clean:
        if search_lower in contact.get("full_name", "").lower():
            matched_contacts.append(contact)
            continue  # Avoid duplicate if also in emails

        for email_entry in contact.get("emails", []):
            if search_lower in (email_entry.get("email", "").lower()):
                matched_contacts.append(contact)
                break

    if search_other_contacts:
        other_contacts_raw = get_other_contacts(contact_service)
        other_contacts_clean = clean_contacts(
            other_contacts_raw, include_source=True, fields=field_to_keep
        )

        for contact in other_contacts_clean:
            if search_lower in contact.get("full_name", "").lower():
                matched_contacts.append(contact)
                continue
            for email_entry in contact.get("emails", []):
                if search_lower in (email_entry.get("email", "").lower()):
                    matched_contacts.append(contact)
                    break

    return matched_contacts


@limit_calls(max_calls=10)
def delete_contact(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    query: str,
):
    account = get_user_service().get_account(
        state["user_id"],
        state["account_name"],
    )

    if not account:
        return {
            "details": f"Please authenticate with Google first in your account: '{state['account_name']}'.",
            "contacts": [],
        }

    try:
        contact_service = build("people", "v1", credentials=account.google_credentials)
        contacts = find_contact_by_query(
            search_name=query,
            contact_service=contact_service,
            search_other_contacts=False,
            field_to_keep=["resourceName"],
        )
    except Exception as e:
        return {
            "details": f"There was an error finding the contact '{query}': {e}",
            "contacts": [],
        }

    if not contacts:
        return {
            "details": f"There are no contacts that match with the query '{query}'.",
            "contacts": [],
        }
    if len(contacts) > 1:
        return {
            "details": f"Please be more specific with the contact name/email, there are multiple contacts found for the query: '{query}'.",
            "contacts": remove_keys_from_contacts(contacts, ["resourceName"]),
        }
    try:
        contact_service.people().deleteContact(
            resourceName=contacts[0]["resourceName"]
        ).execute()
    except Exception as e:
        return {
            "details": f"There was an error deleting the contact: {e}",
            "contacts": remove_keys_from_contacts(contacts, ["resourceName"]),
        }
    return {
        "details": f"Contact '{query}' deleted.",
        "contacts": remove_keys_from_contacts(contacts, ["resourceName"]),
    }


contacts_toolset.append(
    StructuredTool(
        description="Delete a contact from the user's contacts.",
        name="delete_tool",
        func=delete_contact,
        args_schema=DeleteSchema,
    )
)


@limit_calls(max_calls=10)
def create_contact(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    given_name: str,
    family_name: Optional[str] = None,
    emails: Optional[List[str]] = None,
    phones: Optional[List[str]] = None,
):
    account = get_user_service().get_account(
        state["user_id"],
        state["account_name"],
    )

    if not account:
        return {
            "detail": f"Please authenticate with Google first in your account: '{state['account_name']}'.",
            "contacts": [],
        }

    try:
        contact_service = build("people", "v1", credentials=account.google_credentials)

        full_name_to_search = (
            f"{given_name} {family_name}".strip() if family_name else given_name
        )

        contacts = find_contact_by_query(full_name_to_search, contact_service)
        # only exact match
        contacts = [c for c in contacts if c.get("full_name") == full_name_to_search]
        if not contacts and emails:
            for email in emails:
                contacts += find_contact_by_query(email, contact_service)
                if contacts:
                    break
    except Exception as e:
        return {
            "detail": f"There was an error finding the contact '{full_name_to_search}': {e}",
            "contacts": [],
        }

    if contacts:
        return {
            "detail": f"Contact '{full_name_to_search}' already exists.",
            "contacts": contacts,
        }

    contact_data = {
        "names": [
            {
                "givenName": given_name,
                **({"familyName": family_name} if family_name else {}),
            }
        ],
        "emailAddresses": [{"value": email} for email in (emails or [])],
        "phoneNumbers": [{"value": phone} for phone in (phones or [])],
    }
    try:
        new_contact = (
            contact_service.people().createContact(body=contact_data).execute()
        )
    except Exception as e:
        return {
            "detail": f"The contact could not be created: {str(e)}",
            "contacts": [],
        }

    return {
        "detail": f"Contact '{full_name_to_search}' created.",
        "contacts": clean_contacts([new_contact], include_source=False),
    }


contacts_toolset.append(
    StructuredTool(
        description="Create a new contact in the user's contacts.",
        name="create_tool",
        func=create_contact,
        args_schema=CreateSchema,
    )
)


@limit_calls(max_calls=10)
def update_contact(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    query: str,
    new_given_name: Optional[str] = None,
    new_family_name: Optional[str] = None,
    new_emails: List[str] = [],
    new_phones: List[str] = [],
):
    if not new_given_name and not new_family_name and not new_emails and not new_phones:
        return {
            "details": "Please provide at least one field to update.",
            "contacts": [],
        }

    account = get_user_service().get_account(state["user_id"], state["account_name"])

    if not account:
        return {
            "details": f"Please authenticate with Google first in your account: '{state['account_name']}'.",
            "contacts": [],
        }
    try:
        contact_service = build("people", "v1", credentials=account.google_credentials)

        contacts = find_contact_by_query(
            query, contact_service, field_to_keep=["resourceName", "etag"]
        )
    except Exception as e:
        return {
            "details": f"There was an error finding the contact '{query}': {e}",
            "contacts": [],
        }
    if not contacts:
        return {
            "details": f"No contact found matching '{query}'.",
            "contacts": [],
        }
    if len(contacts) > 1:
        return {
            "details": f"Multiple contacts found for '{query}'. Please be more specific.",
            "contacts": remove_keys_from_contacts(contacts, ["resourceName", "etag"]),
        }

    contact = contacts[0]
    resource_name = contact["resourceName"]

    update_fields = []
    update_data = {
        "etag": contact.get("etag"),
    }

    # Update name
    if new_given_name or new_family_name:
        name_data = {}
        if new_given_name:
            name_data["givenName"] = new_given_name
        if new_family_name:
            name_data["familyName"] = new_family_name
        update_data["names"] = [name_data]
        update_fields.append("names")

    # Merge emails
    existing_emails = [e["email"] for e in contact.get("emails", [])]
    all_emails = existing_emails + [e for e in new_emails if e not in existing_emails]
    if all_emails:
        update_data["emailAddresses"] = [{"value": email} for email in all_emails]
        update_fields.append("emailAddresses")

    # Merge phones
    existing_phones = [p["phone"] for p in contact.get("phones", [])]
    all_phones = existing_phones + [p for p in new_phones if p not in existing_phones]
    if all_phones:
        update_data["phoneNumbers"] = [{"value": phone} for phone in all_phones]
        update_fields.append("phoneNumbers")

    try:
        updated_contact = (
            contact_service.people()
            .updateContact(
                resourceName=resource_name,
                updatePersonFields=",".join(update_fields),
                body=update_data,
            )
            .execute()
        )
    except Exception as e:
        return {
            "details": f"There was an error updating the contact: {str(e)}",
            "contacts": [],
        }

    return {
        "details": "Contact updated successfully.",
        "contacts": clean_contacts([updated_contact], include_source=False),
    }


contacts_toolset.append(
    StructuredTool(
        description="Update a contact in the user's contacts.",
        name="update_tool",
        func=update_contact,
        args_schema=UpdateSchema,
    )
)


@limit_calls(max_calls=10)
def get_contacts(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    query: str,
):
    account = get_user_service().get_account(
        state["user_id"],
        state["account_name"],
    )

    if not account:
        return {
            "detail": f"Please authenticate with Google first in your account: '{state['account_name']}'.",
            "contacts": [],
        }

    try:
        contact_service = build("people", "v1", credentials=account.google_credentials)
        contacts = find_contact_by_query(
            query, contact_service, search_other_contacts=True
        )
    except Exception as e:
        return {"detail": f"Error fetching the contacts: {str(e)}", "contacts": []}

    if len(contacts) > MAX_NUM_DISPLAY_ITEMS:
        return {
            "detail": f"There are  {len(contacts)} contacts found matching '{query}'. Showing the first {MAX_NUM_DISPLAY_ITEMS}. Please be more specific.",
            "contacts": contacts[:MAX_NUM_DISPLAY_ITEMS],
        }
    if not contacts:
        return {
            "detail": f"No contacts found matching '{query}'.",
            "contacts": [],
        }
    return {
        "detail": f"Contacts found that match with the query '{query}'.",
        "contacts": contacts,
    }


contacts_toolset.append(
    StructuredTool(
        description="Search for a contact in the user's contacts.",
        name="search_tool",
        func=get_contacts,
        args_schema=SearchSchema,
    )
)
