from typing import Annotated, Optional, List

from langchain_core.tools import InjectedToolCallId
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field


class DeleteSchema(BaseModel):
    query: str = Field(
        description="The query to search for the contact to delete. It can be the name or email of the contact."
    )
    state: Annotated[dict, InjectedState]
    tool_call_id: Annotated[str, InjectedToolCallId]


class CreateSchema(BaseModel):
    given_name: str = Field(description="The given name (first name) of the contact.")
    family_name: Optional[str] = Field(
        default=None, description="The family name (last name) of the contact."
    )
    emails: Optional[List[str]] = Field(
        default_factory=lambda: [],
        description="List of email addresses for the contact.",
    )
    phones: Optional[List[str]] = Field(
        default_factory=lambda: [], description="List of phone numbers for the contact."
    )
    state: Annotated[dict, InjectedState]
    tool_call_id: Annotated[str, InjectedToolCallId]


class UpdateSchema(BaseModel):
    query: str = Field(
        description="Query to identify the contact (can match name or email). This parameter is required."
    )
    new_given_name: Optional[str] = Field(
        default=None, description="New given (first) name for the contact."
    )
    new_family_name: Optional[str] = Field(
        default=None, description="New family (last) name for the contact."
    )
    new_emails: List[str] = Field(
        default_factory=lambda: [], description="List of emails to add to the contact."
    )
    new_phones: List[str] = Field(
        default_factory=lambda: [],
        description="List of phone numbers to add to the contact.",
    )
    state: Annotated[dict, InjectedState]
    tool_call_id: Annotated[str, InjectedToolCallId]


class SearchSchema(BaseModel):
    query: str = Field(
        description="The query to search for the contact. It can be the name or email of the contact."
    )
    state: Annotated[dict, InjectedState]
    tool_call_id: Annotated[str, InjectedToolCallId]
