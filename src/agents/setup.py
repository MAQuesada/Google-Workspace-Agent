from operator import add
from typing import Annotated, Any, Literal, Sequence
from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from pydantic import BaseModel
from langchain_core.messages import AnyMessage
from langgraph.prebuilt import tools_condition


class WorkersState(TypedDict):
    """The state of the worker agents."""

    workers_messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: str
    account_name: str
    num_calls: Annotated[list[str], add]


def tools_condition_worker(
    state: list[AnyMessage] | dict[str, Any] | BaseModel,
    messages_key: str = "workers_messages",
) -> Literal["tools", "__end__"]:
    """Wrapper to use a message_key different from `message`
    in the pre-built `tools_condition` function.
    """
    return tools_condition(state, messages_key)
