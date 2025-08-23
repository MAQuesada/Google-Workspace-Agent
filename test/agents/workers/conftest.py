import base64
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pytest


# =========================
# Shared fake Google "build"
# =========================


class FakeEventsResource:
    def __init__(self, store):
        self.store = store

    # ---- list() ----
    class _ListReq:
        def __init__(self, store, kwargs):
            self.store = store
            self.kwargs = kwargs

        def execute(self):
            return {"items": self.store.get("calendar_list_items", [])}

    def list(self, **kwargs):
        self.store["calendar_last_list_kwargs"] = kwargs
        return self._ListReq(self.store, kwargs)

    # ---- get() ----
    class _GetReq:
        def __init__(self, store, event_id):
            self.store = store
            self.event_id = event_id

        def execute(self):
            ev = self.store.get("calendar_get_event_by_id", {}).get(self.event_id)
            if ev is None:
                raise Exception("Event not found")
            return ev

    def get(self, calendarId, eventId):
        self.store["calendar_last_get"] = {"calendarId": calendarId, "eventId": eventId}
        return self._GetReq(self.store, eventId)

    # ---- delete() ----
    class _DeleteReq:
        def __init__(self, store, event_id):
            self.store = store
            self.event_id = event_id

        def execute(self):
            self.store.setdefault("calendar_deleted_ids", []).append(self.event_id)
            return {}

    def delete(self, calendarId, eventId):
        self.store["calendar_last_delete"] = {
            "calendarId": calendarId,
            "eventId": eventId,
        }
        return self._DeleteReq(self.store, eventId)

    # ---- update() ----
    class _UpdateReq:
        def __init__(self, store, event_id, body, conferenceDataVersion):
            self.store = store
            self.event_id = event_id
            self.body = body
            self.conferenceDataVersion = conferenceDataVersion

        def execute(self):
            self.store.setdefault("calendar_updated_events", {})[self.event_id] = (
                self.body
            )
            out = {
                "id": self.event_id,
                "htmlLink": "https://example/event",
                "start": self.body.get("start", {}),
                "end": self.body.get("end", {}),
                "summary": self.body.get("summary", "Untitled"),
                "attendees": self.body.get("attendees", []),
                "hangoutLink": "https://meet.example",
            }
            if "description" in self.body:
                out["description"] = self.body["description"]
            return out

    def update(self, calendarId, eventId, body, conferenceDataVersion):
        self.store["calendar_last_update"] = {
            "calendarId": calendarId,
            "eventId": eventId,
            "conferenceDataVersion": conferenceDataVersion,
        }
        return self._UpdateReq(self.store, eventId, body, conferenceDataVersion)

    # ---- insert() ----
    class _InsertReq:
        def __init__(self, store, body, conferenceDataVersion):
            self.store = store
            self.body = body
            self.conferenceDataVersion = conferenceDataVersion

        def execute(self):
            new_id = self.store.get("calendar_new_event_id", "evt_created_123")
            out = {
                "id": new_id,
                "htmlLink": "https://example/event",
                "start": self.body.get("start", {}),
                "end": self.body.get("end", {}),
                "summary": self.body.get("summary", "Untitled"),
                "attendees": self.body.get("attendees", []),
                "hangoutLink": "https://meet.example",
            }
            if "description" in self.body:
                out["description"] = self.body["description"]
            self.store.setdefault("calendar_inserted", []).append(out)
            return out

    def insert(self, calendarId, body, conferenceDataVersion):
        self.store["calendar_last_insert"] = {
            "calendarId": calendarId,
            "conferenceDataVersion": conferenceDataVersion,
        }
        return self._InsertReq(self.store, body, conferenceDataVersion)


class FakeFreeBusyResource:
    def __init__(self, store):
        self.store = store

    class _QueryReq:
        def __init__(self, store, body):
            self.store = store
            self.body = body

        def execute(self):
            busy = self.store.get("calendar_busy", [])
            return {"calendars": {"primary": {"busy": busy}}}

    def query(self, body):
        self.store["calendar_last_freebusy_body"] = body
        return self._QueryReq(self.store, body)


class FakeCalendarService:
    def __init__(self, store):
        self.store = store

    def events(self):
        return FakeEventsResource(self.store)

    def freebusy(self):
        return FakeFreeBusyResource(self.store)


# =========================
# People API fake service
# =========================


class _Connections:
    def __init__(self, store):
        self.store = store

    class _ListReq:
        def __init__(self, store, params):
            self.store = store
            self.params = params

        def execute(self):
            connections = self.store.get("people_connections_list", [])
            next_token = self.store.get("people_connections_next_page_token")
            out = {"connections": connections}
            if next_token:
                out["nextPageToken"] = next_token
            return out

    def list(self, **params):
        self.store["people_last_connections_list_params"] = params
        return self._ListReq(self.store, params)


class _OtherContacts:
    def __init__(self, store):
        self.store = store

    class _ListReq:
        def __init__(self, store, params):
            self.store = store
            self.params = params

        def execute(self):
            other_contacts = self.store.get("people_other_contacts_list", [])
            next_token = self.store.get("people_other_contacts_next_page_token")
            out = {"otherContacts": other_contacts}
            if next_token:
                out["nextPageToken"] = next_token
            return out

    def list(self, **params):
        self.store["people_last_other_contacts_list_params"] = params
        return self._ListReq(self.store, params)


class _People:
    def __init__(self, store):
        self.store = store

    def connections(self):
        return _Connections(self.store)

    def otherContacts(self):
        return _OtherContacts(self.store)

    class _CreateContactReq:
        def __init__(self, store, body):
            self.store = store
            self.body = body

        def execute(self):
            new_contact_id = self.store.get(
                "people_new_contact_id", "people_created_123"
            )

            # Generate displayName from givenName and familyName
            names = self.body.get("names", [])
            if names:
                name_data = names[0]
                given_name = name_data.get("givenName", "")
                family_name = name_data.get("familyName", "")
                display_name = f"{given_name} {family_name}".strip()
                names[0]["displayName"] = display_name

            out = {
                "resourceName": new_contact_id,
                "names": names,
                "emailAddresses": self.body.get("emailAddresses", []),
                "phoneNumbers": self.body.get("phoneNumbers", []),
            }
            self.store.setdefault("people_contacts_created", []).append(out)
            return out

    def createContact(self, body):
        self.store["people_last_create_contact_body"] = body
        return self._CreateContactReq(self.store, body)

    class _DeleteContactReq:
        def __init__(self, store, resource_name):
            self.store = store
            self.resource_name = resource_name

        def execute(self):
            self.store.setdefault("people_contacts_deleted", []).append(
                self.resource_name
            )
            return {}

    def deleteContact(self, resourceName):
        self.store["people_last_delete_contact"] = {"resourceName": resourceName}
        return self._DeleteContactReq(self.store, resourceName)

    class _UpdateContactReq:
        def __init__(self, store, resource_name, update_person_fields, body):
            self.store = store
            self.resource_name = resource_name
            self.update_person_fields = update_person_fields
            self.body = body

        def execute(self):
            self.store.setdefault("people_contacts_updated", {})[self.resource_name] = {
                "updatePersonFields": self.update_person_fields,
                "body": self.body,
            }

            # For updates, we need to preserve existing data and merge with new data
            # Find the original contact to preserve existing fields
            original_contact = None
            for contact in self.store.get("people_connections_list", []):
                if contact.get("resourceName") == self.resource_name:
                    original_contact = contact
                    break

            # Start with original contact data
            if original_contact:
                out = {
                    "resourceName": self.resource_name,
                    "names": original_contact.get("names", []),
                    "emailAddresses": original_contact.get("emailAddresses", []),
                    "phoneNumbers": original_contact.get("phoneNumbers", []),
                }
            else:
                out = {
                    "resourceName": self.resource_name,
                    "names": [],
                    "emailAddresses": [],
                    "phoneNumbers": [],
                }

            # Update with new data from body
            if "names" in self.body:
                out["names"] = self.body["names"]
                # Generate displayName if not present
                if out["names"] and "displayName" not in out["names"][0]:
                    name_data = out["names"][0]
                    given_name = name_data.get("givenName", "")
                    family_name = name_data.get("familyName", "")
                    display_name = f"{given_name} {family_name}".strip()
                    out["names"][0]["displayName"] = display_name

            if "emailAddresses" in self.body:
                out["emailAddresses"] = self.body["emailAddresses"]

            if "phoneNumbers" in self.body:
                out["phoneNumbers"] = self.body["phoneNumbers"]

            return out

    def updateContact(self, resourceName, updatePersonFields, body):
        self.store["people_last_update_contact"] = {
            "resourceName": resourceName,
            "updatePersonFields": updatePersonFields,
        }
        return self._UpdateContactReq(
            self.store, resourceName, updatePersonFields, body
        )


class FakePeopleService:
    def __init__(self, store):
        self.store = store

    def people(self):
        return _People(self.store)

    def otherContacts(self):
        return _OtherContacts(self.store)


# =========================
# Gmail fake service
# =========================


class _Messages:
    def __init__(self, store):
        self.store = store

    class _ListReq:
        def __init__(self, store, params):
            self.store = store
            self.params = params

        def execute(self):
            # Single-page by default
            messages = self.store.get("gmail_messages_list", [])
            next_token = self.store.get("gmail_messages_next_page_token")
            out = {"messages": messages}
            if next_token:
                out["nextPageToken"] = next_token
            return out

    def list(self, **params):
        self.store["gmail_last_messages_list_params"] = params
        return self._ListReq(self.store, params)

    class _GetReq:
        def __init__(self, store, userId, msg_id, fmt):
            self.store = store
            self.userId = userId
            self.msg_id = msg_id
            self.fmt = fmt

        def execute(self):
            # Expect the test to preload "gmail_messages_by_id"
            msg = self.store.get("gmail_messages_by_id", {}).get(self.msg_id)
            if msg is None:
                raise Exception("Message not found")
            return msg

    def get(self, userId, id, format="full"):
        return self._GetReq(self.store, userId, id, format)

    class _SendReq:
        def __init__(self, store, userId, body):
            self.store = store
            self.userId = userId
            self.body = body

        def execute(self):
            msg_id = self.store.get("gmail_send_id", "msg_sent_123")
            now_ms = int(
                datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000
            )
            out = {"id": msg_id, "labelIds": ["SENT"], "internalDate": str(now_ms)}
            # Optional: payload can be present if tests need it
            return out

    def send(self, userId, body):
        return self._SendReq(self.store, userId, body)


class _Threads:
    def __init__(self, store):
        self.store = store

    class _ListReq:
        def __init__(self, store, params):
            self.store = store
            self.params = params

        def execute(self):
            threads = self.store.get("gmail_threads_list", [])
            next_token = self.store.get("gmail_threads_next_page_token")
            out = {"threads": threads}
            if next_token:
                out["nextPageToken"] = next_token
            return out

    def list(self, **params):
        self.store["gmail_last_threads_list_params"] = params
        return self._ListReq(self.store, params)

    class _GetReq:
        def __init__(self, store, userId, thread_id, fmt=None):
            self.store = store
            self.userId = userId
            self.thread_id = thread_id
            self.fmt = fmt

        def execute(self):
            thr = self.store.get("gmail_threads_by_id", {}).get(self.thread_id)
            if thr is None:
                raise Exception("Thread not found")
            return thr

    def get(self, userId, id, format="full"):
        return self._GetReq(self.store, userId, id, format)


class _Drafts:
    def __init__(self, store):
        self.store = store

    class _CreateReq:
        def __init__(self, store, userId, body):
            self.store = store
            self.userId = userId
            self.body = body

        def execute(self):
            draft_id = self.store.get("gmail_draft_new_id", "dr_123")
            now_ms = int(
                datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000
            )
            msg = {
                "labelIds": ["DRAFT"],
                "internalDate": str(now_ms),
                "payload": {"parts": []},
            }
            out = {"id": draft_id, "message": msg}
            self.store.setdefault("gmail_drafts_created", []).append(out)
            return out

    def create(self, userId, body):
        return self._CreateReq(self.store, userId, body)

    class _ListReq:
        def __init__(self, store, params):
            self.store = store
            self.params = params

        def execute(self):
            drafts = self.store.get("gmail_drafts_list", [])
            next_token = self.store.get("gmail_drafts_next_page_token")
            out = {"drafts": drafts}
            if next_token:
                out["nextPageToken"] = next_token
            return out

    def list(self, **params):
        self.store["gmail_last_drafts_list_params"] = params
        return self._ListReq(self.store, params)

    class _GetReq:
        def __init__(self, store, userId, draft_id, fmt):
            self.store = store
            self.userId = userId
            self.draft_id = draft_id
            self.fmt = fmt

        def execute(self):
            if self.fmt == "raw":
                # Provide a minimal MIME message base64-encoded
                msg = MIMEMultipart()
                msg["To"] = "to@example.com"
                msg["Subject"] = "Original Subject"
                msg.attach(MIMEText("Original body", "plain"))
                raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
                return {"id": self.draft_id, "message": {"raw": raw}}
            # full
            d = self.store.get("gmail_drafts_by_id_full", {}).get(self.draft_id)
            if d is None:
                # Return a sane default "full" message
                now_ms = int(
                    datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000
                )
                payload = {
                    "headers": [
                        {"name": "To", "value": "to@example.com"},
                        {"name": "Subject", "value": "Draft Subject"},
                        {"name": "From", "value": "me@example.com"},
                    ],
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {
                                "data": base64.urlsafe_b64encode(b"Body").decode()
                            },
                        }
                    ],
                }
                d = {
                    "id": self.draft_id,
                    "message": {
                        "payload": payload,
                        "internalDate": str(now_ms),
                        "labelIds": ["DRAFT"],
                    },
                }
            return d

    def get(self, userId, id, format="full"):
        return self._GetReq(self.store, userId, id, format)

    class _UpdateReq:
        def __init__(self, store, userId, draft_id, body):
            self.store = store
            self.userId = userId
            self.draft_id = draft_id
            self.body = body

        def execute(self):
            now_ms = int(
                datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000
            )
            return {
                "id": self.draft_id,
                "message": {
                    "internalDate": str(now_ms),
                    "labelIds": ["DRAFT"],
                    "payload": {"parts": []},
                },
            }

    def update(self, userId, id, body):
        return self._UpdateReq(self.store, userId, id, body)

    class _DeleteReq:
        def __init__(self, store, userId, draft_id):
            self.store = store
            self.userId = userId
            self.draft_id = draft_id

        def execute(self):
            self.store.setdefault("gmail_drafts_deleted", []).append(self.draft_id)
            return {}

    def delete(self, userId, id):
        return self._DeleteReq(self.store, userId, id)

    class _SendReq:
        def __init__(self, store, userId, body):
            self.store = store
            self.userId = userId
            self.body = body

        def execute(self):
            msg_id = self.store.get("gmail_send_from_draft_id", "msg_sent_from_draft_1")
            return {"id": msg_id}

    def send(self, userId, body):
        return self._SendReq(self.store, userId, body)


class _Users:
    def __init__(self, store):
        self.store = store

    def messages(self):
        return _Messages(self.store)

    def threads(self):
        return _Threads(self.store)

    def drafts(self):
        return _Drafts(self.store)

    class _ProfileReq:
        def __init__(self, store, userId):
            self.store = store
            self.userId = userId

        def execute(self):
            return {
                "emailAddress": self.store.get("gmail_profile_email", "me@example.com")
            }

    def getProfile(self, userId):
        return self._ProfileReq(self.store, userId)


class FakeGmailService:
    def __init__(self, store):
        self.store = store

    def users(self):
        return _Users(self.store)


# =========================
# Pytest fixtures
# =========================


@pytest.fixture
def fake_store():
    """
    Shared mutable store: tests can preload data to drive fakes.
    Keys are namespaced by service (calendar_* and gmail_*).
    """
    return {}


@pytest.fixture
def fake_build(monkeypatch, fake_store):
    """
    Monkeypatch googleapiclient.discovery.build in both modules:
      - agents.calendar.tool_google
      - agents.emails.tools
    to return the appropriate fake service based on api_name.
    """

    def _fake_build(api_name, api_version, credentials=None):
        if api_name == "calendar":
            assert api_version == "v3"
            return FakeCalendarService(fake_store)
        if api_name == "gmail":
            assert api_version == "v1"
            return FakeGmailService(fake_store)
        if api_name == "people":
            assert api_version == "v1"
            return FakePeopleService(fake_store)
        raise AssertionError(f"Unsupported api_name: {api_name}")

    # Patch both modules (adjust paths in your project if needed)
    monkeypatch.setattr("agents.calendar.tool_google.build", _fake_build, raising=True)
    monkeypatch.setattr("agents.emails.tools.build", _fake_build, raising=True)
    monkeypatch.setattr("agents.contacts.tools_google.build", _fake_build, raising=True)
    return _fake_build


@pytest.fixture
def fake_user_service(monkeypatch):
    """
    Monkeypatch get_user_service() in both modules to always return
    an object with a valid account & dummy credentials.
    """

    class Account:
        def __init__(self):
            self.google_credentials = "dummy-creds"

    class FakeUserService:
        def get_account(self, user_id, account_name):
            return Account()

    def _get_user_service():
        return FakeUserService()

    monkeypatch.setattr(
        "agents.calendar.tool_google.get_user_service", _get_user_service, raising=True
    )
    monkeypatch.setattr(
        "agents.emails.tools.get_user_service", _get_user_service, raising=True
    )
    monkeypatch.setattr(
        "agents.contacts.tools_google.get_user_service", _get_user_service, raising=True
    )
    return _get_user_service


@pytest.fixture
def state_ok():
    return {"user_id": "u1", "account_name": "acc1"}
