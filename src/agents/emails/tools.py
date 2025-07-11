import datetime
import re
from email.parser import BytesParser
from email.policy import EmailPolicy
from typing import Annotated, List, Optional
from bs4 import BeautifulSoup
import base64
from langgraph.prebuilt import InjectedState
from langchain_core.tools import StructuredTool, InjectedToolCallId
from googleapiclient.discovery import build
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from email.utils import parseaddr, getaddresses
from google_service.core import get_user_service
from utils.config import get_config

from agents.emails.schemas import (
    SendEmailSchema,
    SearchEmailsSchema,
    ListThreadsSchema,
    FetchMessagesByThreadIdSchema,
    ReplyToThreadSchema,
    CreateDraftSchema,
    ListDraftsSchema,
    EditDraftSchema,
    DeleteDraftSchema,
    SendDraftSchema,
)
from agents.utils import limit_calls


TIMEZONE = get_config().TIMEZONE
MAX_NUM_DISPLAY_ITEMS = get_config().MAX_NUM_DISPLAY_ITEMS
google_emails_toolset = []


@limit_calls(max_calls=10)
def send_email(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    to: str,
    subject: str,
    body: str,
    is_html: bool = True,
    cc: List[str] = [],
) -> dict:
    """
    Sends an email using the Gmail API.

    Args:
        to: Recipient's email address or multiple addresses separated by commas.
        cc: List of email addresses to be added as CC.
        subject: Subject line of the email.
        body: Content of the email body (plain text or HTML).
        is_html: Boolean flag indicating if the body is HTML.
        state: Injected state containing user_id and account_name.

    Returns:
        Dict with details of the operation and list of sent email data.
    """
    account = get_user_service().get_account(
        state["user_id"],
        state["account_name"],
    )

    if not account:
        return {
            "details": f"Please authenticate with Google first for account: '{state['account_name']}'.",
            "emails": [],
        }

    gmail_service = build("gmail", "v1", credentials=account.google_credentials)
    message = MIMEMultipart()
    message["to"] = to
    message["subject"] = subject
    if cc:
        message["cc"] = ", ".join(cc)

    body_content = MIMEText(body, "html" if is_html else "plain")
    message.attach(body_content)

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    try:
        sent_message = (
            gmail_service.users()
            .messages()
            .send(userId="me", body={"raw": raw_message})
            .execute()
        )
        labels = sent_message.get("labelIds", ["SENT"])
        # Genera formato ISO 8601 con segundos
        sent_date = datetime.datetime.now(TIMEZONE).isoformat(timespec="seconds")
        return {
            "details": "Email sent successfully.",
            "emails": [
                {
                    "id": sent_message["id"],
                    "subject": subject,
                    "from": "me",
                    "to": to,
                    "cc": cc,
                    "body": body,
                    "date": sent_date,
                    "labels": labels,
                    "has_attachment": False,
                }
            ],
        }
    except Exception as e:
        return {"details": f"Error sending email: {str(e)}", "emails": []}


google_emails_toolset.append(
    StructuredTool(
        description="Sends an email on behalf of the user.",
        name="send_email_tool",
        func=send_email,
        args_schema=SendEmailSchema,
    )
)


def decode_base64(data):
    """
    Decode Base64 URL-safe data and return it as a string.

    Args:
        data (str): Base64-encoded string.

    Returns:
        str: Decoded string, or empty string if decoding fails.
    """
    try:
        return base64.urlsafe_b64decode(data).decode("utf-8")
    except Exception as e:
        print(f"Error decoding base64 data: {e}")
        return ""


def clean_html(html):
    """
    Clean HTML content and return plain text.

    Args:
        html (str): HTML string.

    Returns:
        str: Plain text extracted from HTML.
    """
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def wrapper_search_emails(payload):
    """
    Extracts and cleans the email body from the payload, preferring plain text if available,
    otherwise extracting text from HTML.

    Args:
        payload (dict): The email payload from Gmail API.

    Returns:
        str: The cleaned email body text, or empty string if no content is found.
    """

    if not isinstance(payload, dict):
        return ""

    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data")
        if data:
            return decode_base64(data)

    elif mime_type == "text/html":
        data = payload.get("body", {}).get("data")
        if data:
            return clean_html(decode_base64(data))

    elif mime_type == "multipart/alternative":
        parts = payload.get("parts", [])

        for part in parts:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data")
                if data:
                    return decode_base64(data)

        for part in parts:
            if part.get("mimeType") == "text/html":
                data = part.get("body", {}).get("data")
                if data:
                    return clean_html(decode_base64(data))

    elif mime_type.startswith("multipart/"):
        parts = payload.get("parts", [])
        if parts:
            return wrapper_search_emails(parts[0])

    return ""


def has_attachments_recursive(parts):
    """
    Recursively checks if any part or subpart has an attachment.

    Args:
        parts (list): List of message parts from the Gmail API payload.

    Returns:
        bool: True if any part has an attachment, False otherwise.
    """
    for part in parts:
        if part.get("body", {}).get("attachmentId"):
            return True
        if "parts" in part:
            if has_attachments_recursive(part["parts"]):
                return True
    return False


@limit_calls(max_calls=10)
def search_emails(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: dict,
    query: Optional[str] = None,
    label_ids: List[str] = [],
    specific_message_ids: List[str] = [],
    has_attachment: bool = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """
    Searches for emails matching a query using the Gmail API.

    Args:
        query (str): Search query string for filtering emails.
        label_ids (List[str]): Labels to filter emails.
        specific_message_ids (List[str]): List of specific message IDs to retrieve. If provided, other parameters are ignored.
        has_attachment (bool): If true, filters only emails with attachments.
        start_date (str): Start date filter (YYYY-MM-DD).
        end_date (str): End date filter (YYYY-MM-DD).
        state (dict): Injected state containing user_id and account_name.

    Returns:
        Dict[str, List[Dict[str, str]]]: A dictionary with details and matching emails.
    """
    account = get_user_service().get_account(
        state["user_id"],
        state["account_name"],
    )
    if not account:
        return {
            "details": f"Please authenticate with Google first for account: '{state['account_name']}'.",
            "emails": [],
        }

    gmail_service = build("gmail", "v1", credentials=account.google_credentials)

    try:
        total_count = 0
        message_ids = []
        if not specific_message_ids:
            search_query = query or ""

            if has_attachment:
                if not search_query:
                    search_query = "has:attachment"
                else:
                    search_query += " has:attachment"

            if start_date:  # time in timestamps UNIX format
                try:
                    start_dt_naive = datetime.datetime.strptime(start_date, "%Y-%m-%d")
                    start_dt = TIMEZONE.localize(start_dt_naive)
                    start_timestamp = int(start_dt.timestamp())
                    search_query += f" after:{start_timestamp}"
                except ValueError:
                    return {
                        "details": "Invalid start_date format. Use YYYY-MM-DD.",
                        "emails": [],
                    }

            if end_date:  # time in timestamps UNIX format
                try:
                    end_dt_naive = datetime.datetime.strptime(
                        end_date, "%Y-%m-%d"
                    ).replace(hour=23, minute=59, second=59)
                    end_dt = TIMEZONE.localize(end_dt_naive)
                    end_timestamp = int(end_dt.timestamp())
                    search_query += f" before:{end_timestamp}"
                except ValueError:
                    return {
                        "details": "Invalid end_date format. Use YYYY-MM-DD.",
                        "emails": [],
                    }

            search_params = {"userId": "me", "maxResults": 500}
            if search_query.strip():
                search_params["q"] = search_query.strip()
            if label_ids:
                search_params["labelIds"] = label_ids

            next_page_token = None

            while True:
                if next_page_token:
                    search_params["pageToken"] = next_page_token
                results = (
                    gmail_service.users().messages().list(**search_params).execute()
                )
                messages = results.get("messages", [])
                total_count += len(messages)
                message_ids.extend([msg["id"] for msg in messages])
                next_page_token = results.get("nextPageToken")
                if not next_page_token:
                    break
        else:
            message_ids.extend(specific_message_ids)
            total_count = len(message_ids)
        cleaned_emails = []
        for msg_id in message_ids[:MAX_NUM_DISPLAY_ITEMS]:
            msg_details = (
                gmail_service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )
            payload = msg_details.get("payload", {})
            headers = {
                h["name"].lower(): h["value"] for h in payload.get("headers", [])
            }

            # Extract and clean email body using the wrapper
            body = wrapper_search_emails(payload)
            # Remove extra spaces and newlines
            cleaned_body = re.sub(r"\s+", " ", body).strip()

            # Extract recipient info
            to_addresses = [
                addr[1] for addr in getaddresses([headers.get("to", "")]) if addr[1]
            ]
            if not to_addresses and "reply-to" in headers:
                to_addresses = [
                    addr[1] for addr in getaddresses([headers["reply-to"]]) if addr[1]
                ]
            to_address_str = (
                ", ".join(to_addresses) if to_addresses else headers.get("to", "")
            )

            cc_addresses = [
                parseaddr(cc.strip())[1]
                for cc in headers.get("cc", "").split(",")
                if cc.strip()
            ]

            labels = msg_details.get("labelIds", [])

            # Parse email date
            try:
                internal_date = msg_details.get("internalDate")
                date = (
                    datetime.datetime.fromtimestamp(
                        int(internal_date) / 1000, tz=TIMEZONE
                    ).isoformat()
                    if internal_date
                    else datetime.datetime.now(TIMEZONE).isoformat(timespec="seconds")
                )
            except Exception:
                date = "Invalid Date"

            has_attachments = has_attachments_recursive(payload.get("parts", []))

            cleaned_emails.append(
                {
                    "id": msg_id,
                    "subject": headers.get("subject", "No Subject"),
                    "from": parseaddr(headers.get("from", ""))[1] or "Unknown sender",
                    "to": to_address_str or "No recipient",
                    "cc": cc_addresses,
                    "body": cleaned_body or None,
                    "thread_id": msg_details.get("threadId", "No Thread ID"),
                    "labels": labels,
                    "date": date,
                    "has_attachments": has_attachments,
                }
            )

        details = f"Found {total_count} emails matching query."
        if total_count > MAX_NUM_DISPLAY_ITEMS:
            details += f" Showing first {MAX_NUM_DISPLAY_ITEMS} emails. For more results, refine your search criteria."

        return {
            "details": details,
            "emails": cleaned_emails,
        }
    except Exception as e:
        return {"details": f"Error fetching emails: {str(e)}", "emails": []}


google_emails_toolset.append(
    StructuredTool(
        description="Fetches emails based on a search query.",
        name="fetch_emails_tool",
        func=search_emails,
        args_schema=SearchEmailsSchema,
    )
)


@limit_calls(max_calls=10)
def list_threads(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    query: Optional[str] = None,
    label_ids: List[str] = [],
    has_attachment: bool = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """
    Lists the user's email conversation threads from Gmail with advanced search capabilities and pagination.
    Only the first message of each thread is shown, with the body cleaned using wrapper_search_emails.
    Args:
        state: Injected state containing user_id and account_name.
        query: Search query string for filtering threads.
        label_ids: Labels to filter threads (e.g., 'INBOX', 'UNREAD').
        has_attachment: If true, filters threads with attachments.
        start_date: Start date filter (YYYY-MM-DD).
        end_date: End date filter (YYYY-MM-DD).

    Returns:
        Dict with details of the operation and list of thread data.
    """
    account = get_user_service().get_account(
        state["user_id"],
        state["account_name"],
    )
    if not account:
        return {
            "details": f"Please authenticate with Google first for account: '{state['account_name']}'.",
            "threads": [],
        }

    gmail_service = build("gmail", "v1", credentials=account.google_credentials)
    try:
        search_query = query or ""
        if has_attachment:
            if not search_query:
                search_query = "has:attachment"
            else:
                search_query += " has:attachment"
        if start_date:
            try:
                start_dt_naive = datetime.datetime.strptime(start_date, "%Y-%m-%d")
                start_dt = TIMEZONE.localize(start_dt_naive)
                start_timestamp = int(start_dt.timestamp())
                search_query += f" after:{start_timestamp}"
            except ValueError:
                return {
                    "details": "Invalid start_date format. Use YYYY-MM-DD.",
                    "threads": [],
                }
        if end_date:
            try:
                end_dt_naive = datetime.datetime.strptime(end_date, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59
                )
                end_dt = TIMEZONE.localize(end_dt_naive)
                end_timestamp = int(end_dt.timestamp())
                search_query += f" before:{end_timestamp}"
            except ValueError:
                return {
                    "details": "Invalid end_date format. Use YYYY-MM-DD.",
                    "threads": [],
                }
            # API request parameters
        search_params = {"userId": "me", "maxResults": 500}
        if search_query.strip():
            search_params["q"] = search_query.strip()
        if label_ids:
            search_params["labelIds"] = label_ids

        next_page_token = None
        total_count = 0
        thread_ids = []

        while True:
            if next_page_token:
                search_params["pageToken"] = next_page_token
            results = gmail_service.users().threads().list(**search_params).execute()
            threads = results.get("threads", [])
            total_count += len(threads)
            thread_ids.extend([thread["id"] for thread in threads])
            next_page_token = results.get("nextPageToken")
            if not next_page_token or len(thread_ids) >= MAX_NUM_DISPLAY_ITEMS:
                break

        thread_ids = thread_ids[:MAX_NUM_DISPLAY_ITEMS]
        # Get thread details and extract only the first message
        cleaned_threads = []
        for thread_id in thread_ids:
            thread_details = (
                gmail_service.users()
                .threads()
                .get(userId="me", id=thread_id, format="full")
                .execute()
            )

            messages = thread_details.get("messages", [])
            if not messages:
                continue

            # Sort messages by date to get the most recent one
            messages.sort(key=lambda x: int(x.get("internalDate", 0)), reverse=True)
            first_message = messages[0]

            # Extract and clean the message body using wrapper_search_emails
            body = wrapper_search_emails(first_message.get("payload", {}))

            # Extract other details
            headers = {
                h["name"].lower(): h["value"]
                for h in first_message.get("payload", {}).get("headers", [])
            }
            has_attachments = has_attachments_recursive(
                first_message.get("payload", {}).get("parts", [])
            )
            try:
                internal_date = first_message.get("internalDate")
                date = (
                    datetime.datetime.fromtimestamp(
                        int(internal_date) / 1000, tz=TIMEZONE
                    ).isoformat()
                    if internal_date
                    else datetime.datetime.now(TIMEZONE).isoformat(timespec="seconds")
                )
            except (ValueError, TypeError):
                date = "Invalid Date"

            thread_dict = {
                "thread_id": thread_id,
                "message_id": first_message["id"],
                "subject": headers.get("subject", "No Subject"),
                "from": headers.get("from", "Unknown Sender"),
                "to": headers.get("to", "No Recipient"),
                "date": date,
                "labels": first_message.get("labelIds", []),
                "body": body,
                "has_attachments": has_attachments,
                "message_count": len(messages),
            }

            cleaned_threads.append(thread_dict)

        details = f"Found {total_count} conversation threads."
        if total_count > MAX_NUM_DISPLAY_ITEMS:
            details += f" Showing first {MAX_NUM_DISPLAY_ITEMS} threads. Refine your search for more results."

        return {
            "details": details,
            "emails": cleaned_threads,
        }
    except Exception as e:
        return {"details": f"Error listing threads: {str(e)}", "emails": []}


google_emails_toolset.append(
    StructuredTool(
        description="Lists the user's email conversation threads.",
        name="list_threads_tool",
        func=list_threads,
        args_schema=ListThreadsSchema,
    )
)


@limit_calls(max_calls=10)
def fetch_messages_by_thread_id(
    thread_id: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
):
    """
    Fetches all messages from a specific Gmail thread.

    Args:
        thread_id: ID of the thread to fetch messages from.
        state: Injected state containing user_id and account_name.

    Returns:
        Dict with details of the operation and list of message data.
    """
    account = get_user_service().get_account(
        state["user_id"],
        state["account_name"],
    )
    if not account:
        return {
            "details": f"Please authenticate with Google first for account: '{state['account_name']}'.",
            "emails": [],
        }

    gmail_service = build("gmail", "v1", credentials=account.google_credentials)
    try:
        thread = (
            gmail_service.users().threads().get(userId="me", id=thread_id).execute()
        )
        messages = thread.get("messages", [])

        cleaned_emails = []
        for email in messages:
            headers = {
                h["name"].lower(): h["value"]
                for h in email.get("payload", {}).get("headers", [])
            }

            try:
                internal_date = email.get("internalDate")
                date = (
                    datetime.datetime.fromtimestamp(
                        int(internal_date) / 1000, tz=TIMEZONE
                    ).isoformat()
                    if internal_date
                    else datetime.datetime.now(TIMEZONE).isoformat(timespec="seconds")
                )
            except Exception:
                date = "Invalid Date"

            has_attachments = has_attachments_recursive(
                email.get("payload", {}).get("parts", [])
            )

            email_dict = {
                "id": email.get("id", "No ID"),
                "subject": headers.get("subject", "No Subject"),
                "from": headers.get("from", "Unknown Sender"),
                "to": headers.get("to", "No Recipient"),
                "body": email.get("snippet", "No Content"),
                "labels": email.get("labelIds", []),
                "thread_id": email.get("threadId", "No Thread ID"),
                "date": date,
                "has_attachments": has_attachments,
            }
            cleaned_emails.append(email_dict)

        return {
            "details": f"Found {len(messages)} messages in thread.",
            "emails": cleaned_emails,
        }
    except Exception as e:
        return {"details": f"Error fetching thread messages: {str(e)}", "emails": []}


google_emails_toolset.append(
    StructuredTool(
        description="Fetches messages from a specific email thread.",
        name="fetch_message_by_thread_id_tool",
        func=fetch_messages_by_thread_id,
        args_schema=FetchMessagesByThreadIdSchema,
    )
)


@limit_calls(max_calls=10)
def reply_to_thread(
    thread_id: str,
    body: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    is_html: bool = True,
):
    """
    Sends a reply to an existing Gmail thread.

    Args:
        thread_id: ID of the thread to reply to.
        body: Content of the reply message.
        state: Injected state containing user_id and account_name.
        is_html: Whether the body content should be sent as HTML. Default is True.

    Returns:
        Dict with details of the operation and list of sent reply data.
    """

    account = get_user_service().get_account(
        state["user_id"],
        state["account_name"],
    )
    if not account:
        return {
            "details": f"Please authenticate with Google first for account: '{state['account_name']}'.",
            "emails": [],
        }

    gmail_service = build("gmail", "v1", credentials=account.google_credentials)

    try:
        profile = gmail_service.users().getProfile(userId="me").execute()
        user_email = profile["emailAddress"].lower()

        thread = (
            gmail_service.users().threads().get(userId="me", id=thread_id).execute()
        )

        messages = thread["messages"]

        for msg in reversed(messages):
            headers = msg["payload"]["headers"]
            from_header = next((h for h in headers if h["name"] == "From"), None)
            if not from_header:
                continue

            decoded_from = "".join(
                part.decode(encoding or "utf-8") if isinstance(part, bytes) else part
                for part, encoding in decode_header(from_header["value"])
            )
            _, sender_email = parseaddr(decoded_from)
            sender_email = sender_email.lower()

            if sender_email != user_email:
                to_addr = sender_email
                original_message = msg
                break
        else:
            return {
                "details": "No valid recipients found in the thread.",
                "emails": [],
            }

        subject_header = next(
            (h for h in headers if h["name"] == "Subject"), {"value": ""}
        )
        subject_value = subject_header["value"]
        decoded_subject = "".join(
            part.decode(encoding or "utf-8") if isinstance(part, bytes) else part
            for part, encoding in decode_header(subject_value)
        )
        subject = f"Re: {decoded_subject}" if decoded_subject else "Re: Follow Up"

        message = MIMEMultipart()
        message["to"] = to_addr
        message["subject"] = subject
        message["In-Reply-To"] = original_message["id"]
        message["References"] = original_message["id"]

        message.attach(MIMEText(body, "html" if is_html else "plain"))

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        reply_message = (
            gmail_service.users()
            .messages()
            .send(userId="me", body={"raw": raw, "threadId": thread_id})
            .execute()
        )

        labels = reply_message.get("labelIds", ["SENT"])

        try:
            internal_date = reply_message.get("internalDate")
            date = (
                datetime.datetime.fromtimestamp(
                    int(internal_date) / 1000, tz=TIMEZONE
                ).isoformat()
                if internal_date
                else datetime.datetime.now(TIMEZONE).isoformat(timespec="seconds")
            )
        except Exception:
            date = "Invalid Date"

        has_attachments = False
        payload = reply_message.get("payload", {})
        parts = payload.get("parts", [])
        for part in parts:
            if part.get("filename") and part.get("body", {}).get("attachmentId"):
                has_attachments = True
                break

        return {
            "details": "Reply sent successfully.",
            "emails": [
                {
                    "id": reply_message["id"],
                    "subject": subject,
                    "from": "me",
                    "to": to_addr,
                    "body": body,
                    "labels": labels,
                    "date": date,
                    "has_attachments": has_attachments,
                }
            ],
        }
    except Exception as e:
        return {"details": f"Error replying to thread: {str(e)}", "emails": []}


google_emails_toolset.append(
    StructuredTool(
        description="Replies to an existing email thread.",
        name="reply_to_thread_tool",
        func=reply_to_thread,
        args_schema=ReplyToThreadSchema,
    )
)


@limit_calls(max_calls=10)
def create_draft(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    to: str,
    subject: str,
    body: str,
    is_html: bool = True,
    cc: List[str] = [],
):
    """
    Creates an email draft in Gmail with optional HTML formatting and CC recipients.

    Args:
        to: Recipient's email address or multiple addresses separated by commas.
        cc: List of email addresses to be added as CC.
        subject: Subject line of the draft.
        body: Content of the draft body (plain text or HTML).
        is_html: Boolean flag indicating if the body is HTML.
        state: Injected state containing user_id and account_name.

    Returns:
        Dict with details of the operation and list of draft data.
    """
    account = get_user_service().get_account(
        state["user_id"],
        state["account_name"],
    )
    if not account:
        return {
            "details": f"Please authenticate with Google first for account: '{state['account_name']}'.",
            "emails": [],
        }

    gmail_service = build("gmail", "v1", credentials=account.google_credentials)
    message = MIMEMultipart()
    message["to"] = to
    message["subject"] = subject
    if cc:
        message["cc"] = ", ".join(cc)

    body_content = MIMEText(body, "html" if is_html else "plain")
    message.attach(body_content)
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    try:
        draft = (
            gmail_service.users()
            .drafts()
            .create(userId="me", body={"message": {"raw": raw_message}})
            .execute()
        )

        message_data = draft.get("message", {})
        labels = message_data.get("labelIds", ["DRAFT"])

        try:
            internal_date = message_data.get("internalDate")
            date = (
                datetime.datetime.fromtimestamp(
                    int(internal_date) / 1000, tz=TIMEZONE
                ).isoformat()
                if internal_date
                else datetime.datetime.now(TIMEZONE).isoformat(timespec="seconds")
            )
        except Exception:
            date = "Invalid Date"

        has_attachments = any(
            part.get("filename") and part.get("body", {}).get("attachmentId")
            for part in message_data.get("payload", {}).get("parts", [])
        )

        return {
            "details": "Draft created successfully.",
            "emails": [
                {
                    "id": draft["id"],
                    "subject": subject,
                    "from": "me",
                    "to": to,
                    "cc": cc,
                    "body": body,
                    "labels": labels,
                    "date": date,
                    "has_attachments": has_attachments,
                }
            ],
        }
    except Exception as e:
        return {"details": f"Error creating draft: {str(e)}", "emails": []}


google_emails_toolset.append(
    StructuredTool(
        description="Creates an email draft.",
        name="create_draft_tool",
        func=create_draft,
        args_schema=CreateDraftSchema,
    )
)


@limit_calls(max_calls=10)
def list_drafts(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    query: Optional[str] = None,
    has_attachment: bool = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    specific_draft_ids: Optional[List[str]] = None,
) -> dict:
    """
    Lists the user's email drafts from Gmail or fetches specific drafts by their IDs.

    Args:
        state: Injected state containing user_id and account_name.
        query: Search query string for filtering drafts.
        has_attachment: If true, only return drafts with attachments.
        start_date: Filter drafts created after this date (YYYY-MM-DD).
        end_date: Filter drafts created before this date (YYYY-MM-DD).
        specific_draft_ids: List of specific draft IDs to fetch. If provided, other filters are ignored.

    Returns:
        Dict with details of the operation and list of draft data.
    """
    account = get_user_service().get_account(
        state["user_id"],
        state["account_name"],
    )
    if not account:
        return {
            "details": f"Please authenticate with Google first for account: '{state['account_name']}'.",
            "emails": [],
        }

    gmail_service = build("gmail", "v1", credentials=account.google_credentials)

    try:
        if specific_draft_ids:
            draft_ids = specific_draft_ids
            total_count = len(draft_ids)
        else:
            search_query = query or ""
            if has_attachment:
                if not search_query:
                    search_query = "has:attachment"
                else:
                    search_query += " has:attachment"
            if start_date:
                try:
                    start_dt_naive = datetime.datetime.strptime(start_date, "%Y-%m-%d")
                    start_dt = TIMEZONE.localize(start_dt_naive)
                    start_timestamp = int(start_dt.timestamp())
                    search_query += f" after:{start_timestamp}"
                except ValueError:
                    return {
                        "details": "Invalid start_date format. Use YYYY-MM-DD.",
                        "emails": [],
                    }
            if end_date:
                try:
                    end_dt_naive = datetime.datetime.strptime(
                        end_date, "%Y-%m-%d"
                    ).replace(hour=23, minute=59, second=59)
                    end_dt = TIMEZONE.localize(end_dt_naive)
                    end_timestamp = int(end_dt.timestamp())
                    search_query += f" before:{end_timestamp}"
                except ValueError:
                    return {
                        "details": "Invalid end_date format. Use YYYY-MM-DD.",
                        "emails": [],
                    }

            search_params = {"userId": "me", "maxResults": 500}
            if search_query.strip():
                search_params["q"] = search_query.strip()

            next_page_token = None
            draft_ids = []
            while True:
                if next_page_token:
                    search_params["pageToken"] = next_page_token
                results = gmail_service.users().drafts().list(**search_params).execute()
                drafts = results.get("drafts", [])
                draft_ids.extend([draft["id"] for draft in drafts])
                next_page_token = results.get("nextPageToken")
                if not next_page_token:
                    break
            total_count = len(draft_ids)
        if total_count == 0:
            return {
                "details": "No drafts found matching the query.",
                "emails": [],
            }

        cleaned_drafts = []
        for draft_id in draft_ids[:MAX_NUM_DISPLAY_ITEMS]:
            try:
                draft_data = (
                    gmail_service.users()
                    .drafts()
                    .get(userId="me", id=draft_id, format="full")
                    .execute()
                )
                message = draft_data["message"]
                headers = {
                    h["name"].lower(): h["value"] for h in message["payload"]["headers"]
                }

                body = ""
                parts_for_body = message["payload"].get("parts", [message["payload"]])
                for part in parts_for_body:
                    if part["mimeType"] == "text/plain" and "data" in part.get(
                        "body", {}
                    ):
                        body += base64.urlsafe_b64decode(part["body"]["data"]).decode()
                    elif part.get("mimeType") == "text/html":
                        body += base64.urlsafe_b64decode(part["body"]["data"]).decode()

                to_addresses = [
                    addr[1] for addr in getaddresses([headers.get("to", "")]) if addr[1]
                ]
                if not to_addresses and "reply-to" in headers:
                    to_addresses = [
                        addr[1]
                        for addr in getaddresses([headers["reply-to"]])
                        if addr[1]
                    ]
                to_address_str = (
                    ", ".join(to_addresses) if to_addresses else headers.get("to", "")
                )

                cc_addresses = [
                    parseaddr(cc.strip())[1]
                    for cc in headers.get("cc", "").split(",")
                    if cc.strip()
                ]

                labels = message.get("labelIds", ["DRAFT"])
                try:
                    internal_date = message.get("internalDate")
                    date = (
                        datetime.datetime.fromtimestamp(
                            int(internal_date) / 1000, tz=TIMEZONE
                        ).isoformat()
                        if internal_date
                        else datetime.datetime.now(TIMEZONE).isoformat(
                            timespec="seconds"
                        )
                    )
                except Exception:
                    date = "Invalid Date"

                has_attachments = has_attachments_recursive(
                    message["payload"].get("parts", [])
                )

                cleaned_drafts.append(
                    {
                        "id": draft_data["id"],
                        "subject": headers.get("subject", "No Subject"),
                        "from": parseaddr(headers.get("from", ""))[1]
                        or "Unknown sender",
                        "to": to_address_str or "No recipient",
                        "cc": cc_addresses,
                        "body": body.strip(),
                        "labels": labels,
                        "date": date,
                        "has_attachments": has_attachments,
                    }
                )
            except Exception as e:
                print(f"Error fetching draft {draft_id}: {str(e)}")
                continue

        details = f"Found {total_count} drafts."
        if total_count > MAX_NUM_DISPLAY_ITEMS:
            details += f" Showing first {MAX_NUM_DISPLAY_ITEMS} drafts. Refine your search for more results."

        return {
            "details": details,
            "emails": cleaned_drafts,
        }

    except Exception as e:
        return {"details": f"Error listing drafts: {str(e)}", "emails": []}


google_emails_toolset.append(
    StructuredTool(
        description="Lists the user's email drafts or fetches specific drafts by their IDs.",
        name="list_drafts_tool",
        func=list_drafts,
        args_schema=ListDraftsSchema,
    )
)

utf8_policy = EmailPolicy(utf8=True, cte_type="8bit", linesep="\r\n")


@limit_calls(max_calls=10)
def edit_draft(
    draft_id: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    subject: Optional[str] = None,
    to: Optional[str] = None,
    cc: Optional[List[str]] = None,
    body: Optional[str] = None,
    is_html: Optional[bool] = None,
):
    """
    Edits an existing Gmail draft with optional updates.

    Args:
        draft_id: ID of the draft to edit.
        state: Injected state containing user_id and account_name.
        subject: New subject for the draft (optional).
        to: New recipient email or multiple addresses separated by commas (optional).
        cc: New list of CC recipients (optional).
        body: New email body content (optional).
        is_html: Flag indicating if body is HTML or plain text (optional).

    Returns:
        Dict with details of the operation and list of updated draft data.
    """
    account = get_user_service().get_account(
        state["user_id"],
        state["account_name"],
    )
    if not account:
        return {
            "details": f"Please authenticate with Google first for account: '{state['account_name']}'.",
            "emails": [],
        }

    if not any([subject, to, cc, body, is_html]):
        return {"details": "No updates provided", "emails": []}

    gmail_service = build("gmail", "v1", credentials=account.google_credentials)

    try:
        draft_data = (
            gmail_service.users()
            .drafts()
            .get(userId="me", id=draft_id, format="raw")
            .execute()
        )

        raw_message = base64.urlsafe_b64decode(draft_data["message"]["raw"])
        msg = BytesParser(policy=utf8_policy).parsebytes(raw_message)

        if subject:
            if "Subject" in msg:
                msg.replace_header("Subject", subject)
            else:
                msg.add_header("Subject", subject)
        if to:
            if "To" in msg:
                msg.replace_header("To", to)
            else:
                msg.add_header("To", to)
        if cc is not None:
            if cc:
                formatted_cc = ", ".join([email.strip() for email in cc if email])
                if formatted_cc:
                    if "Cc" in msg:
                        msg.replace_header("Cc", formatted_cc)
                    else:
                        msg.add_header("Cc", formatted_cc)
            else:
                if "Cc" in msg:
                    del msg["Cc"]
        if body:
            content_type = (
                "html" if (is_html if is_html is not None else True) else "plain"
            )
            new_body_part = MIMEText(body, content_type)
            if msg.is_multipart():
                msg.set_payload([])
                msg.attach(new_body_part)
            else:
                msg.set_payload([new_body_part])

        new_raw = base64.urlsafe_b64encode(msg.as_bytes(policy=utf8_policy)).decode(
            "utf-8"
        )
        updated_draft = (
            gmail_service.users()
            .drafts()
            .update(userId="me", id=draft_id, body={"message": {"raw": new_raw}})
            .execute()
        )

        message_data = updated_draft.get("message", {})
        labels = message_data.get("labelIds", ["DRAFT"])

        try:
            internal_date = message_data.get("internalDate")
            date = (
                datetime.datetime.fromtimestamp(
                    int(internal_date) / 1000, tz=TIMEZONE
                ).isoformat()
                if internal_date
                else datetime.datetime.now(TIMEZONE).isoformat(timespec="seconds")
            )
        except Exception:
            date = "Invalid Date"

        has_attachments = has_attachments_recursive(
            message_data.get("payload", {}).get("parts", [])
        )

        return {
            "details": "Draft updated successfully",
            "emails": [
                {
                    "id": updated_draft["id"],
                    "subject": msg.get("Subject", "No Subject"),
                    "from": "me",
                    "to": msg.get("To", "No recipient"),
                    "cc": msg.get("Cc", "").split(", ") if msg.get("Cc") else [],
                    "body": body or None,
                    "labels": labels,
                    "date": date,
                    "has_attachments": has_attachments,
                }
            ],
        }
    except Exception as e:
        return {"details": f"Error editing draft: {str(e)}", "emails": []}


google_emails_toolset.append(
    StructuredTool(
        description="Edits an existing draft while preserving attachments and formatting",
        name="edit_draft_tool",
        func=edit_draft,
        args_schema=EditDraftSchema,
    )
)


@limit_calls(max_calls=10)
def delete_draft(
    draft_ids: List[str],
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
):
    """
    Permanently deletes a list of Gmail drafts without prior checks.

    Args:
        draft_ids: List of draft IDs to delete.
        state: Injected state containing user_id and account_name.

    Returns:
        Dict with details of the operations.
    """
    account = get_user_service().get_account(state["user_id"], state["account_name"])
    if not account:
        return {"details": "Authentication required", "emails": []}

    gmail_service = build("gmail", "v1", credentials=account.google_credentials)

    deleted_ids = []
    errors = []

    for draft_id in draft_ids:
        try:
            gmail_service.users().drafts().delete(userId="me", id=draft_id).execute()
            deleted_ids.append(draft_id)
        except Exception as e:
            errors.append(f"Error deleting draft {draft_id}: {str(e)}")

    details = f"Deleted {len(deleted_ids)} drafts successfully."
    if errors:
        details += f" Failed to delete {len(errors)} drafts: {', '.join(errors)}"

    return {"details": details, "emails": []}


google_emails_toolset.append(
    StructuredTool(
        description="Permanently deletes a specified draft",
        name="delete_draft_tool",
        func=delete_draft,
        args_schema=DeleteDraftSchema,
    )
)


@limit_calls(max_calls=10)
def send_draft(
    draft_id: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
):
    """
    Sends an existing Gmail draft given its IDs.

    Args:
        draft_id: ID of the draft to send.
        state: Injected state containing user_id and account_name.

    Returns:
        Dict with details of the operation and sent message data.
    """
    account = get_user_service().get_account(state["user_id"], state["account_name"])
    if not account:
        return {
            "details": f"Authentication required for '{state['account_name']}'",
            "emails": [],
        }

    gmail_service = build("gmail", "v1", credentials=account.google_credentials)

    try:
        sent_message = (
            gmail_service.users()
            .drafts()
            .send(userId="me", body={"id": draft_id})
            .execute()
        )

        message = (
            gmail_service.users()
            .messages()
            .get(userId="me", id=sent_message["id"], format="full")
            .execute()
        )

        headers = {h["name"].lower(): h["value"] for h in message["payload"]["headers"]}
        parts = message["payload"].get("parts", [message["payload"]])

        body = ""
        for part in parts:
            if part["mimeType"] == "text/plain" and "data" in part.get("body", {}):
                body += base64.urlsafe_b64decode(part["body"]["data"]).decode()

        to_addresses = [
            addr[1] for addr in getaddresses([headers.get("to", "")]) if addr[1]
        ]
        if not to_addresses and "reply-to" in headers:
            to_addresses = [
                addr[1] for addr in getaddresses([headers["reply-to"]]) if addr[1]
            ]
        to_address_str = (
            ", ".join(to_addresses) if to_addresses else headers.get("to", "")
        )
        from_address = parseaddr(headers.get("from", ""))[1] or "Unknown sender"

        labels = message.get("labelIds", ["SENT"])
        try:
            internal_date = message.get("internalDate")
            date = (
                datetime.datetime.fromtimestamp(
                    int(internal_date) / 1000, tz=TIMEZONE
                ).isoformat()
                if internal_date
                else datetime.datetime.now(TIMEZONE).isoformat(timespec="seconds")
            )
        except Exception:
            date = "Invalid Date"

        has_attachments = has_attachments_recursive(message["payload"].get("parts", []))

        return {
            "details": "Draft sent successfully",
            "emails": [
                {
                    "id": sent_message["id"],
                    "subject": headers.get("subject", "No Subject"),
                    "from": from_address,
                    "to": to_address_str,
                    "cc": [
                        parseaddr(cc.strip())[1]
                        for cc in headers.get("cc", "").split(",")
                        if cc.strip()
                    ],
                    "body": body.strip(),
                    "thread_id": message.get("threadId", ""),
                    "labels": labels,
                    "date": date,
                    "has_attachments": has_attachments,
                }
            ],
        }
    except Exception as e:
        return {"details": f"Sending failed: {str(e)}", "emails": []}


google_emails_toolset.append(
    StructuredTool(
        description="Sends an existing email draft.",
        name="send_draft_tool",
        func=send_draft,
        args_schema=SendDraftSchema,
    )
)
