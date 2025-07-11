from operator import add
from typing import Annotated, Sequence
from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class WorkersState(TypedDict):
    """The state of the worker agents."""

    workers_messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: str
    account_name: str
    num_calls: Annotated[list[str], add]
