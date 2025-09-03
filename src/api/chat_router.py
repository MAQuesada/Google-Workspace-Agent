import json
import re
from typing import Any, AsyncGenerator

from anyio import to_thread
from fastapi import APIRouter, Depends
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from agents.orchestrator.core import get_agent
from google_service.core import get_user_service
from utils.logger import get_logger

from api.validations import validate_user_input

logger = get_logger("api.chat_router")


def extract_user_request(text: str) -> str:
    """
    Extracts the user's request from the given formatted text.
    """
    pattern = r"### The user's request is:\n(.*?)\n\n---"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


UPDATE_MESSAGES = {
    "orchestrator_input": "⏳ Processing the request...",
    "email_manage": "✉️ Managing emails...",
    "date_manage": " 🕐 Managing dates...",
    "contacts_manage": "👥 Managing your contacts...",
    "calendar_manage": "📅 Managing your calendars...",
    "search_manage": "🔍 Searching for information...",
    "llm_with_gmail_tools": "🛠️ Selecting email tools...",
    "llm_with_contact_tools": "🛠️ Selecting contact tools...",
    "llm_with_calendar_tools": "🛠️ Selecting calendar tools...",
    "feedback_synthesizer": "✨ Crafting a response...",
}

router = APIRouter(prefix="/chat", tags=["chat"])


def get_conversation_id(username: str, conversation_id: str) -> str:
    return f"{username}::{conversation_id}"


class ChatRequest(BaseModel):
    username: str = Field(..., description="User identifier")
    conversation_id: str = Field(..., description="Conversation identifier")
    message: str = Field("", description="User message")


async def event_generator(
    *,
    message: str,
    username: str,
    conversation_id: str,
    orchestrator_graph: Any,
) -> AsyncGenerator[str, None]:
    """SSE generator that relays orchestrator events."""
    update_messages = UPDATE_MESSAGES.copy()
    try:
        async for event in orchestrator_graph.astream_events(
            {"user_input": message, "user_id": username},
            {"configurable": {"thread_id": conversation_id}},
        ):
            event_type: str | None = event.get("event")
            metadata: dict[str, Any] = event.get("metadata") or {}
            data: dict[str, Any] = event.get("data") or {}
            langgraph_node: str | None = metadata.get("langgraph_node")
            name: str | None = event.get("name")
            data_chunk = data.get("chunk")
            if event_type == "on_chain_start" and langgraph_node in update_messages:
                response_event = {
                    "type": "progress",
                    "data": update_messages[langgraph_node],
                }
                yield f"data: {json.dumps(response_event)}\n\n"
                update_messages.pop(langgraph_node, None)

            elif (
                event_type == "on_chat_model_stream"
                and langgraph_node == "orchestrator_output"
            ):
                # data_chunk may be an object with `.content` or a dict with "content"
                content = getattr(data_chunk, "content", None)
                if content is None and isinstance(data_chunk, dict):
                    content = data_chunk.get("content")
                if content:
                    response_event = {"type": "content", "data": content}
                    yield f"data: {json.dumps(response_event)}\n\n"

            elif event_type == "on_tool_start" and name:
                response_event = {"type": "progress", "data": f"🔧 Using **{name}**"}
                yield f"data: {json.dumps(response_event)}\n\n"
    except Exception as e:
        logger.exception(
            "Error while streaming chat events.",
            extra={"exception": str(e)},
        )
        response = {
            "type": "error",
            "data": "An error occurred while processing your request. Please try again or if the problem persists, contact support.",
        }
        yield f"data: {json.dumps(response)}\n\n"
    else:
        logger.info(
            "Chat request processed successfully.",
            extra={"username": username, "conversation_id": conversation_id},
        )


@router.post("", response_class=StreamingResponse)
async def chat_post(
    body: ChatRequest,
    orchestrator_graph: Any = Depends(get_agent),
):
    """
    POST /chat

    Body (JSON):
    {
      "username": "user123",
      "conversation_id": "conv-1",
      "message": "Hello"
    }
    """
    logger.info(
        "Chat request received.",
        extra={"username": body.username, "conversation_id": body.conversation_id},
    )

    # Run sync services in a worker thread to avoid blocking the event loop.
    related_accounts = await to_thread.run_sync(
        get_user_service().list_accounts, body.username
    )

    if not related_accounts:
        logger.info(
            "No accounts associated with user.", extra={"username": body.username}
        )
        response = {
            "type": "content",
            "data": "🚨 You have no accounts associated with your user.",
        }
        return StreamingResponse(
            f"data: {json.dumps(response)}\n\n",
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )
    validation_result = validate_user_input(body.message)
    if not validation_result.safe:
        logger.warning(
            "User input validation failed.",
            extra={"validation_failed": validation_result.error_message},
        )
        response = {
            "type": "error",
            "data": validation_result.error_message,
        }
        return StreamingResponse(
            f"data: {json.dumps(response)}\n\n",
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )
    gen = event_generator(
        message=body.message,
        username=body.username,
        conversation_id=get_conversation_id(body.username, body.conversation_id),
        orchestrator_graph=orchestrator_graph,
    )

    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/history")
async def get_history(
    username: str,
    conversation_id: str,
):
    logger.info(
        "Getting history for user.",
        extra={"username": username, "conversation_id": conversation_id},
    )
    related_accounts = await to_thread.run_sync(
        get_user_service().list_accounts, username
    )

    if not related_accounts:
        logger.info("No accounts associated with user.", extra={"username": username})
        return []

    config = {
        "configurable": {"thread_id": get_conversation_id(username, conversation_id)}
    }
    orchestrator_graph = get_agent()
    messages = orchestrator_graph.get_state(config).values.get("messages", [])
    history = []
    for message in messages:
        if isinstance(message, HumanMessage):
            history.append(
                {"role": "user", "content": extract_user_request(str(message.content))}
            )
        elif isinstance(message, AIMessage):
            history.append({"role": "assistant", "content": message.content})
    logger.info(
        "History retrieved successfully.",
        extra={"username": username, "conversation_id": conversation_id},
    )
    return history
