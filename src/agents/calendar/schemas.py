from typing import Annotated, Optional, List

from langchain_core.tools import InjectedToolCallId
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field


class FindEventSchema(BaseModel):
    tool_call_id: Annotated[str, InjectedToolCallId]
    state: Annotated[dict, InjectedState]
    query: Optional[str] = Field(
        default=None,
        description="Search term to find events that match these terms in the event's title, description, location, attendee's, attendee's email, organizer's name, organizer's email, etc. Please provide a string.",
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Lower bound (exclusive) for an event's start time to filter by. Accepts ISO format with timezone (e.g., '2024-12-06T06:00:00+01:00' or '2025-05-07T00:00:00+02:00').This is a required field.",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="Upper bound (exclusive) for an event's end time to filter by. Accepts ISO format with timezone (e.g., '2024-12-06T20:00:00+01:00' or '2025-05-07T00:00:00+02:00').",
    )
    timezone: str = Field(
        default="Europe/Paris",
        description="Time zone used in the response. Default is 'Europe/Paris'.",
    )


class FreeSlotsSchema(BaseModel):
    tool_call_id: Annotated[str, InjectedToolCallId]
    state: Annotated[dict, InjectedState]
    start_date: str = Field(
        ...,
        description="Start of the search range in ISO format with timezone (e.g., '2024-12-06T06:00:00+01:00' or '2025-05-07T00:00:00+02:00'). This is a required field.",
    )
    end_date: str = Field(
        ...,
        description="End of the search range in ISO format with timezone (e.g., '2024-12-06T06:00:00+01:00' or '2025-05-07T00:00:00+02:00'). This is a required field.",
    )
    timezone: str = Field(
        default="Europe/Paris",
        description="Time zone used in the response. Optional. The default is 'Europe/Paris' timezone.",
    )
    min_duration: int = Field(
        default=30,
        description="Minimum duration in minutes for a slot to be considered free. The default is 30 minutes.",
    )


class DeleteEventSchema(BaseModel):
    tool_call_id: Annotated[str, InjectedToolCallId]
    state: Annotated[dict, InjectedState]
    event_id_or_event_link: Optional[str] = Field(
        default=None,
        description="The ID of the event to delete or the full Google Calendar event link. This field is required if the query, start date, and end date are not provided. Please provide a value of type string.",
    )
    query: Optional[str] = Field(
        default=None,
        description="Search term to find events that match these terms in the event's title, description, location, attendee's displayName, attendee's email, organizer's displayName, organizer's email, etc if needed. Please provide a value of type string.",
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Lower bound (inclusive) for an event's start time to filter by. Accepts ISO format with timezone (e.g., '2024-12-06T06:00:00+01:00' or '2025-05-07T00:00:00+02:00').",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="Upper bound (exclusive) for an event's end time to filter by. Accepts ISO format with timezone (e.g., '2024-12-06T20:00:00+01:00' or '2025-05-07T00:00:00+02:00').",
    )


class UpdateEventSchema(BaseModel):
    tool_call_id: Annotated[str, InjectedToolCallId]
    state: Annotated[dict, InjectedState]
    event_id_or_event_link: str = Field(
        ...,
        description="ID of the event or the full Google Calendar event link to be updated. This parameter is required.",
    )
    start_datetime: Optional[str] = Field(
        default=None,
        description="The (inclusive) start time of the event. Accepts ISO format with timezone (e.g., '2024-12-06T06:00:00+01:00' or '2025-05-07T00:00:00+02:00').",
    )
    title: Optional[str] = Field(default=None, description="Title of the event.")
    description: Optional[str] = Field(
        default=None, description="Description of the event."
    )
    attendees: Optional[List[str]] = Field(
        default=None,
        description="List of attendee emails to add to the event. If not provided, existing attendees will be kept.",
    )
    create_meeting_room: bool = Field(
        default=False,
        description="If true, a Google Meet link is created and added to the event.",
    )
    event_duration_hour: int = Field(default=0, description="Number of hours (0-24).")
    event_duration_minutes: int = Field(
        default=0, description="Number of minutes (0-59)."
    )
    ignore_conflicts: bool = Field(
        default=False,
        description="If true, the event will be updated even if there are conflicts with other events. The default is false (if conflicts are detected, the event won't be updated).",
    )
    timezone: str = Field(
        default="Europe/Paris",
        description="Time zone used in the response. Optional. The default is 'Europe/Paris' timezone.",
    )


class CreateEventSchema(BaseModel):
    tool_call_id: Annotated[str, InjectedToolCallId]
    state: Annotated[dict, InjectedState]
    start_datetime: str = Field(
        ...,
        description="The (inclusive) start time of the event. This parameter is required. Accepts ISO format with timezone (e.g., '2024-12-06T06:00:00+01:00' or '2025-05-07T00:00:00+02:00').",
    )
    title: str = Field(
        ..., description="Title of the event. This parameter is required."
    )
    description: Optional[str] = Field(
        default=None, description="Description of the event."
    )
    attendees: Optional[List[str]] = Field(
        default=None,
        description="List of exact attendee emails that will have access to the event.",
    )
    create_meeting_room: bool = Field(
        default=True,
        description="If true, a Google Meet link is created and added to the event.",
    )
    event_duration_hour: int = Field(default=0, description="Number of hours (0-24).")
    event_duration_minutes: int = Field(
        default=30, description="Number of minutes (0-59). The default is 30 minutes."
    )
    ignore_conflicts: bool = Field(
        default=False,
        description="If true, the event will be created even if there are conflicts with other events. The default is false (if conflicts are detected, the event won't be created).",
    )
