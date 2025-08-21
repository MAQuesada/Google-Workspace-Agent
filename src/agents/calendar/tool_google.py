from langchain_core.tools.base import InjectedToolCallId
import urllib.parse
import base64
from datetime import datetime, timedelta
from typing import Annotated, List
from typing import Optional
import uuid
from langgraph.prebuilt import InjectedState
from langchain_core.tools import StructuredTool
from googleapiclient.discovery import build
from agents.calendar.schemas import (
    FindEventSchema,
    FreeSlotsSchema,
    DeleteEventSchema,
    UpdateEventSchema,
    CreateEventSchema,
)
from google_service.core import get_user_service
from agents.utils import limit_calls

calendar_toolset_google = []


def get_event_id(event_input: str):
    """
    Extracts the event ID from a Google Calendar event link or returns it directly
    if the input is already an event ID.

    Args:
        event_input (str): A full Google Calendar event URL or a direct event ID.

    Returns:
        str or None: The extracted event ID if successful, otherwise None.

    Raises:
        Excepction: If the input is not a valid URL or event ID.
    """
    # Quick check: if it's a direct ID (no URL structure), return it
    if "http" not in event_input and "eid=" not in event_input:
        return event_input.strip()

    # Parse the URL and extract the 'eid' parameter
    parsed_url = urllib.parse.urlparse(event_input)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    eid = query_params.get("eid", [""])[0]
    if not eid:
        raise Exception("Invalid URL: 'eid' parameter not found")

    # Decode Base64 URL-safe string, add padding if needed
    padding = "=" * (-len(eid) % 4)
    decoded_bytes = base64.urlsafe_b64decode(eid + padding)
    decoded_str = decoded_bytes.decode("utf-8")
    # The format is "<event_id> <calendar_id>", so we return the first part
    return decoded_str.split()[0]


def clean_event(event_list: list[dict], fields=[]):
    """Extract the 'title', 'start', 'end', 'event_link', 'attendees'
    and 'meet_link' from the event list and return a list of dictionaries
    with this information.
    Also extracts the fields specified in the 'fields' parameter.

    Args:
    event_list (list): List of events to clean.
    fields (list): List of fields to extract from the events.
    """

    cleaned_events = []
    for event in event_list:
        cleaned_event = {
            "title": event.get("summary", "Untitled"),
            "start": (
                event.get("start", {}).get("dateTime", None)
                or event.get("start", {}).get("date", None)
            ),
            "end": (
                event.get("end", {}).get("dateTime", None)
                or event.get("end", {}).get("date", None)
            ),
            "event_link": event.get("htmlLink", None),
            "attendees": event.get("attendees", []),
            "meet_link": event.get("hangoutLink", None),
        }
        for field in fields:
            cleaned_event[field] = event.get(field, None)
        cleaned_events.append(cleaned_event)
    return cleaned_events


def find_event(
    calendar_service,
    query: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timezone: str = "Europe/Paris",
) -> list:
    """
    Find events that match the search terms or fall within the date range
    provided.

    Args:
        query : Search term to find events that match these terms in
        the event's title, description, location, attendee's displayName,
        attendee's email, organizer's displayName, organizer's email,
        etc if needed. Please provide a value of type string.
        start_date: Lower bound (exclusive) for an event's start time to filter by. Accepts ISO format  with timezone (e.g., "2024-12-06T06:00:00+01:00" or 2025-05-07T00:00:00+02:00).
        end_date: Upper bound (exclusive) for an event's end time to filter by. Accepts ISO format with timezone (e.g., 2024-12-06T20:00:00+01:00 or 2025-05-07T00:00:00+02:00).
        timezone: Time zone used in the response. Optional. The default is "Europe/Paris" timezone.
    """

    events_result = (
        calendar_service.events()
        .list(
            calendarId="primary",
            timeMin=start_date,
            timeMax=end_date,
            singleEvents=True,
            maxResults=15,
            q=query,
            timeZone=timezone,
            orderBy="startTime",
        )
        .execute()
    )

    return events_result.get("items", [])


@limit_calls(max_calls=10)
def get_events(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    query: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timezone: str = "Europe/Paris",
) -> dict:
    """
    Wrapper around find_event to handle errors and return structured responses.

    Args:
    query : Search term to find events.
    start_date: Lower bound for event's start time in ISO format.
    end_date: Upper bound for event's end time in ISO format.
    timezone: Time zone used in the response (default: "Europe/Paris").

    Returns:
    A dictionary containing either the list of events found or an error message.
    """
    if not start_date and not end_date and not query:
        return {
            "details": "Please provide the `query` to search for events or  `start_date` and `end_date` to filter events by date.",
            "events": [],
        }

    account = get_user_service().get_account(
        state["user_id"],
        state["account_name"],
    )

    if not account:
        return {
            "details": f"Please authenticate with Google first in your account: '{state['account_name']}'.",
            "events": [],
        }
    calendar_service = build("calendar", "v3", credentials=account.google_credentials)

    try:
        events = find_event(calendar_service, query, start_date, end_date, timezone)
        if not events:
            return {
                "details": f"No events found with the query '{query}' between '{start_date}' and '{end_date}'.",
                "events": [],
            }
        return {
            "details": "Events found successfully.",
            "events": clean_event(events, fields=["description"]),
        }
    except Exception as e:
        return {"details": f"Error while retrieving events: {e}", "events": []}


calendar_toolset_google.append(
    StructuredTool(
        description="Finds events in a Google Calendar and returns structured results, handling errors if they occur.",
        name="get_events",
        func=get_events,
        args_schema=FindEventSchema,
    )
)


@limit_calls(max_calls=10)
def find_free_slots(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    start_date: str,
    end_date: str,
    timezone: str = "Europe/Paris",
    min_duration: int = 30,
) -> dict:
    """
    Finds Free Slots in a Google Calendar based On  a specific time period.

    Args:
    start_date: Start of the search range in ISO format with timezone (e.g., "2024-12-06T06:00:00+01:00" or 2025-05-07T00:00:00+02:00).
    end_date: End of the search range in ISO format with timezone (e.g., "2024-12-06T06:00:00+01:00" or 2025-05-07T00:00:00+02:00).
    timezone: Time zone used in the response. Optional. The default is "Europe/Paris" timezone.
    min_duration: Minimum duration in minutes for a slot to be considered free. The default is 30 minutes.

    Returns:
    Dict with the details of the operation and a list of free slots found.
    """

    account = get_user_service().get_account(
        state["user_id"],
        state["account_name"],
    )

    if not account:
        return {
            "details": f"Please authenticate with Google first in your account: '{state['account_name']}'.",
            "events": [],
        }
    calendar_service = build("calendar", "v3", credentials=account.google_credentials)
    try:
        freebusy_result = (
            calendar_service.freebusy()
            .query(
                body={
                    "timeMin": start_date,
                    "timeMax": end_date,
                    "timeZone": timezone,
                    "items": [{"id": "primary"}],
                }
            )
            .execute()
        )

        busy_slots = freebusy_result["calendars"]["primary"].get("busy", [])

        free_slots = []
        current_time = datetime.fromisoformat(start_date)

        for busy in busy_slots:
            busy_start = datetime.fromisoformat(busy["start"])
            busy_end = datetime.fromisoformat(busy["end"])

            # If there's a gap before this busy period, add it as free time
            if (busy_start - current_time).total_seconds() / 60 >= min_duration:
                free_slots.append(
                    {"start": current_time.isoformat(), "end": busy_start.isoformat()}
                )

            # Update current time to the end of the busy period
            current_time = max(current_time, busy_end)

        # Check for free time at the end of the range
        end_datetime = datetime.fromisoformat(end_date)
        if (end_datetime - current_time).total_seconds() / 60 >= min_duration:
            free_slots.append(
                {"start": current_time.isoformat(), "end": end_datetime.isoformat()}
            )

        return {"details": "Free slots found.", "free_slots": free_slots}
    except Exception as e:
        return {"details": f"Error while getting the free slots: {e}", "free_slots": []}


calendar_toolset_google.append(
    StructuredTool(
        description="Finds Free Slots in a Google Calendar based On  a specific time period.",
        name="find_free_slots",
        func=find_free_slots,
        args_schema=FreeSlotsSchema,
    )
)


@limit_calls(max_calls=10)
def delete_event(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    event_id_or_event_link: Optional[str] = None,
    query: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """
    Deletes an event from a Google Calendar.

    Args:
    event_id_or_event_link: The ID of the event to delete or the full Google Calendar event link. This field is required if the query, start date, and end date are not provided. Please provide a value of type string.
    query: Search term to find events that match these terms in the event's title, description, location, attendee's displayName, attendee's email, organizer's displayName, organizer's email, etc if needed. Please provide a value of type string.
    start_date: Lower bound (exclusive) for an event's start time to filter by. Accepts ISO format with timezone (e.g., '2024-12-06T06:00:00+01:00' or '2025-05-07T00:00:00+02:00').
    end_date: Upper bound (exclusive) for an event's end time to filter by. Accepts ISO format with timezone (e.g., '2024-12-06T20:00:00+01:00' or '2025-05-07T00:00:00+02:00').

    Returns:
    Dict with the details of the operation and the result of the deletion.
    """

    account = get_user_service().get_account(
        state["user_id"],
        state["account_name"],
    )

    if not account:
        return {
            "details": f"Please authenticate with Google first in your account: '{state['account_name']}'.",
            "events": [],
        }
    calendar_service = build("calendar", "v3", credentials=account.google_credentials)

    if event_id_or_event_link:
        try:
            try:
                event_id = get_event_id(event_id_or_event_link)
            except Exception as e:
                return {
                    "details": f"Error while extracting the event ID: {e}",
                    "events": [],
                }
            calendar_service.events().delete(
                calendarId="primary", eventId=event_id
            ).execute()
            return {
                "details": f"Event with ID '{event_id}' deleted successfully.",
                "events": [],
            }
        except Exception as e:
            return {
                "details": f"There was an error deleting the event: {e}",
                "events": [],
            }

    if not start_date and not end_date and not query:
        return {
            "details": "Please provide the event ID/link or the query, start date, and end date to search for events.",
            "events": [],
        }

    try:
        events = find_event(calendar_service, query, start_date, end_date)
    except Exception as e:
        return {
            "details": f"There was an error searching for the event to delete: {e}",
            "events": [],
        }

    if not events:
        return {
            "details": f"No events found with the query '{query}' between '{start_date}' and '{end_date}'.",
            "events": [],
        }

    if len(events) > 1:
        return {
            "details": "Please be more specific with the parameters query, start date, and end date. Multiple events found.",
            "events": clean_event(events),
        }

    event_id = events[0]["id"]
    try:
        calendar_service.events().delete(
            calendarId="primary", eventId=event_id
        ).execute()
    except Exception as e:
        return {
            "details": f"There was an error deleting the event: {e}",
            "events": clean_event(events),
        }

    return {"details": "Event deleted successfully.", "events": clean_event(events)}


calendar_toolset_google.append(
    StructuredTool(
        description="Deletes an event from a Google Calendar based on the event id or event link. If the event id is not provided, it will search for events based on the query, start date, and end date.",
        name="delete_event",
        func=delete_event,
        args_schema=DeleteEventSchema,
    )
)


@limit_calls(max_calls=10)
def update_event(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    event_id_or_event_link: str,
    start_datetime: Optional[str] = None,
    title: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    create_meeting_room: bool = False,
    event_duration_hour: int = 0,
    event_duration_minutes: int = 0,
    ignore_conflicts: bool = False,
    description: Optional[str] = None,
    timezone: str = "Europe/Paris",
) -> dict:
    """
    Updates an event in a Google Calendar.

    Args:
    event_id_or_event_link: The ID of the event or the full Google Calendar event link to be updated. This parameter is required.
    start_datetime: The (inclusive) start time of the event. Accepts ISO format with timezone.
    title: Title of the event.
    attendees: List of attendee emails.
    create_meeting_room: If true, a Google Meet link is created and added to the event.
    event_duration_hour: Number of hours (0-24).
    event_duration_minutes: Number of minutes (0-59).
    ignore_conflicts: If true, the event will be updated even if there are conflicts.
    description: Optional description of the event.

    Returns:
    Dict with the details of the operation and the events related.
    """

    account = get_user_service().get_account(
        state["user_id"],
        state["account_name"],
    )

    if not account:
        return {
            "details": f"Please authenticate with Google first in your account: '{state['account_name']}'.",
            "events": [],
        }

    calendar_service = build("calendar", "v3", credentials=account.google_credentials)

    try:
        try:
            event_id = get_event_id(event_id_or_event_link)
        except Exception as e:
            return {
                "details": f"Error while extracting the event ID: {e}",
                "events": [],
            }
        event = (
            calendar_service.events()
            .get(calendarId="primary", eventId=event_id)
            .execute()
        )
    except Exception as e:
        return {
            "details": f"There was an error retrieving the event: {e}",
            "events": [],
        }

    # Update fields if provided
    if title:
        event["summary"] = title
    if description:
        event["description"] = description
    if start_datetime:
        event["start"] = {"dateTime": start_datetime}

    start_dt = event["start"].get("dateTime")

    if event_duration_hour > 0 or event_duration_minutes > 0:
        if not start_dt:
            return {
                "details": "Start datetime of the event is required to calculate the end time.",
                "events": [],
            }
        end_datetime = datetime.fromisoformat(start_dt) + timedelta(
            hours=event_duration_hour, minutes=event_duration_minutes
        )
        event["end"] = {"dateTime": end_datetime.isoformat()}

    if (
        start_datetime is None
        and event_duration_hour == 0
        and event_duration_minutes == 0
    ):
        ignore_conflicts = (
            True  # the event time is not changed, so no conflicts to check
        )

    if not ignore_conflicts and start_dt is not None:
        conflicts = find_event(
            calendar_service,
            start_date=start_dt,
            end_date=event["end"]["dateTime"],
        )
        real_conflicts = [
            ev
            for ev in conflicts
            if ev["id"] != event_id and ev["start"].get("dateTime", None) is not None
        ]
        if real_conflicts:
            return {
                "details": "The event cannot be updated due to conflicts with the following events.",
                "events": clean_event(real_conflicts),
            }

    if attendees is not None:
        current_attendees = event.get("attendees", [])
        current_emails = {att["email"] for att in current_attendees if "email" in att}
        new_emails = set(attendees) - current_emails

        new_attendees = [{"email": email} for email in new_emails]
        event["attendees"] = current_attendees + new_attendees

    if create_meeting_room:
        event["conferenceData"] = {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }

    try:
        updated_event = (
            calendar_service.events()
            .update(
                calendarId="primary",
                eventId=event_id,
                body=event,
                conferenceDataVersion=1,
            )
            .execute()
        )
    except Exception as e:
        return {"details": f"There was an error updating the event: {e}", "events": []}

    return {
        "details": "Event updated successfully.",
        "events": clean_event([updated_event], fields=["description"]),
    }


calendar_toolset_google.append(
    StructuredTool(
        description="Updates/Modify an event in a Google Calendar given the event ID.",
        name="update_event",
        func=update_event,
        args_schema=UpdateEventSchema,
    )
)


@limit_calls(max_calls=10)
def create_event(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    start_datetime: str,
    title: str,
    attendees: Optional[List[str]] = None,
    create_meeting_room: bool = True,
    event_duration_hour: int = 0,
    event_duration_minutes: int = 30,
    ignore_conflicts: bool = False,
    description: Optional[str] = None,
) -> dict:
    """
    Creates an event in Google Calendar.

    Args:
    start_datetime: The (inclusive) start time of the event in ISO format with timezone.
    title: Title of the event.
    attendees: List of attendee emails.
    create_meeting_room: If true, a Google Meet link is created and added to the event.
    event_duration_hour: Number of hours (0-24).
    event_duration_minutes: Number of minutes (0-59).
    ignore_conflicts: If true, the event will be created even if there are conflicts.
    description: Optional description of the event.

    Returns:
    Dict with the details of the operation and the created event.
    """

    account = get_user_service().get_account(
        state["user_id"],
        state["account_name"],
    )

    if not account:
        return {
            "details": f"Please authenticate with Google first in your account: '{state['account_name']}'.",
            "events": [],
        }

    calendar_service = build("calendar", "v3", credentials=account.google_credentials)

    # Calculate end time
    start_time = datetime.fromisoformat(start_datetime)
    end_time = start_time + timedelta(
        hours=event_duration_hour, minutes=event_duration_minutes
    )

    event = {
        "summary": title,
        "start": {"dateTime": start_datetime},
        "end": {"dateTime": end_time.isoformat()},
        "attendees": [{"email": email} for email in attendees] if attendees else [],
    }

    if description:
        event["description"] = description

    if create_meeting_room:
        event["conferenceData"] = {
            "createRequest": {
                "requestId": "sample123",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }

    if not ignore_conflicts:
        conflicts = find_event(
            calendar_service, start_date=start_datetime, end_date=end_time.isoformat()
        )
        real_conflicts = [
            ev for ev in conflicts if ev["start"].get("dateTime", None) is not None
        ]
        if real_conflicts:
            return {
                "details": "The event cannot be created due to conflicts with existing events.",
                "events": clean_event(conflicts),
            }

    try:
        created_event = (
            calendar_service.events()
            .insert(calendarId="primary", body=event, conferenceDataVersion=1)
            .execute()
        )
    except Exception as e:
        return {"details": f"There was an error creating the event: {e}", "events": []}

    return {
        "details": "Event created successfully.",
        "events": clean_event([created_event], fields=["description"]),
    }


calendar_toolset_google.append(
    StructuredTool(
        description="Creates an event in Google Calendar based on the provided parameters.",
        name="create_event",
        func=create_event,
        args_schema=CreateEventSchema,
    )
)
