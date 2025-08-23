from typing import Annotated, List, Optional

from langchain_core.tools import InjectedToolCallId
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field


class SendEmailSchema(BaseModel):
    tool_call_id: Annotated[str, InjectedToolCallId]
    to: str = Field(
        description="Recipient's email address or multiple addresses separated by commas"
    )
    cc: List[str] = Field(
        default=[],
        description="Email addresses of the recipients to be added as a carbon copy (CC).",
    )
    subject: str = Field(description="Email subject.")
    body: str = Field(
        description="Body content of the email. Can be plain text or HTML. This parameter is required."
    )
    is_html: bool = Field(
        default=True,
        description="Indicates whether the email body is HTML or plain text.",
    )
    state: Annotated[dict, InjectedState]


class SearchEmailsSchema(BaseModel):
    """
    Schema for searching emails using Gmail API.
    """

    tool_call_id: Annotated[str, InjectedToolCallId]
    specific_message_ids: Optional[List[str]] = Field(
        default=None,
        description="IDs of the messages to retrieve. If provided, other filters are ignored.",
    )

    query: Optional[str] = Field(
        default=None, description="Only return messages matching the specified query."
    )

    label_ids: List[str] = Field(
        description="Filter messages by their label IDs. Only return messages with labels that match all of the specified label IDs. For example, specifying 'INBOX' will return only messages in the inbox. If you specify both 'INBOX' and 'SENT', you will get an empty list, as no message can belong to both labels simultaneously. Labels identify the status or category of messages. Some built-in labels include: 'INBOX', 'SENT', 'SPAM', 'TRASH', 'UNREAD', 'STARRED', 'IMPORTANT', and 'CATEGORY_PERSONAL'"
    )
    has_attachment: bool = Field(
        default=False,
        description="If true, only return emails that contain attachments.",
    )
    start_date: Optional[str] = Field(
        default=None, description="Filter emails received after this date (YYYY-MM-DD)."
    )
    end_date: Optional[str] = Field(
        default=None,
        description="Filter emails received before this date (YYYY-MM-DD).",
    )
    state: Annotated[dict, InjectedState]


class ListThreadsSchema(BaseModel):
    tool_call_id: Annotated[str, InjectedToolCallId]
    query: Optional[str] = Field(
        default=None, description="Search query string for filtering threads."
    )
    label_ids: List[str] = Field(
        default=[],
        description="Filter threads by their label IDs (e.g., 'INBOX', 'UNREAD').",
    )
    has_attachment: bool = Field(
        default=False, description="If true, only return threads with attachments."
    )
    start_date: Optional[str] = Field(
        default=None, description="Filter threads after this date (YYYY-MM-DD)."
    )
    end_date: Optional[str] = Field(
        default=None, description="Filter threads before this date (YYYY-MM-DD)."
    )
    state: Annotated[dict, InjectedState]


class FetchMessagesByThreadIdSchema(BaseModel):
    tool_call_id: Annotated[str, InjectedToolCallId]
    thread_id: str = Field(description="ID of the thread to fetch messages from.")
    state: Annotated[dict, InjectedState]


class ReplyToThreadSchema(BaseModel):
    tool_call_id: Annotated[str, InjectedToolCallId]
    thread_id: str = Field(description="ID of the thread to reply to.")
    body: str = Field(description="Reply body content.")
    state: Annotated[dict, InjectedState]
    is_html: bool = Field(
        default=True,
        description="Indicates whether the email body is HTML or plain text.",
    )


class CreateDraftSchema(BaseModel):
    tool_call_id: Annotated[str, InjectedToolCallId]
    to: str = Field(
        description="Recipient's email address or multiple addresses separated by commas."
    )
    cc: List[str] = Field(
        default=[],
        description="Email addresses of the recipients to be added as a carbon copy (CC).",
    )
    subject: str = Field(description="Draft subject.")
    body: str = Field(description="Draft body content. Can be plain text or HTML.")
    is_html: bool = Field(
        default=True,
        description="Indicates whether the email body is HTML or plain text.",
    )
    state: Annotated[dict, InjectedState]


class ListDraftsSchema(BaseModel):
    tool_call_id: Annotated[str, InjectedToolCallId]
    query: Optional[str] = Field(
        default=None, description="Search query string for filtering drafts."
    )
    has_attachment: bool = Field(
        default=False, description="If true, only return drafts with attachments."
    )
    start_date: Optional[str] = Field(
        default=None, description="Filter drafts created after this date (YYYY-MM-DD)."
    )
    end_date: Optional[str] = Field(
        default=None, description="Filter drafts created before this date (YYYY-MM-DD)."
    )
    specific_draft_ids: Optional[List[str]] = Field(
        default=None,
        description="List of specific draft IDs to fetch. If provided, other filters are ignored.",
    )
    state: Annotated[dict, InjectedState]


class EditDraftSchema(BaseModel):
    tool_call_id: Annotated[str, InjectedToolCallId]
    draft_id: str = Field(description="ID of the draft to edit")
    subject: Optional[str] = Field(
        default=None, description="New subject for the draft (optional)"
    )
    to: Optional[str] = Field(
        default=None,
        description="New recipient email or multiple addresses separated by commas (optional)",
    )
    cc: Optional[List[str]] = Field(
        default=None, description="New list of CC recipients (optional)"
    )
    body: Optional[str] = Field(
        default=None, description="New email body content (optional)"
    )
    is_html: Optional[bool] = Field(
        default=None,
        description="Flag indicating if body is HTML or plain text (optional)",
    )
    state: Annotated[dict, InjectedState]


class DeleteDraftSchema(BaseModel):
    tool_call_id: Annotated[str, InjectedToolCallId]
    draft_ids: List[str] = Field(description="List of draft IDs to delete")
    state: Annotated[dict, InjectedState]


class SendDraftSchema(BaseModel):
    tool_call_id: Annotated[str, InjectedToolCallId]
    draft_id: str = Field(description="ID of the draft to send.")
    state: Annotated[dict, InjectedState]


class SaveAttachmentsSchema(BaseModel):
    tool_call_id: Annotated[str, InjectedToolCallId]
    email_id: str = Field(description="ID of the email containing attachments")
    state: Annotated[dict, InjectedState]
    target_folder: Optional[str] = Field(
        "Email Attachments", description="Name of the target Drive folder"
    )
