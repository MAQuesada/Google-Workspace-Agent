from typing import Protocol, runtime_checkable
import asyncio

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from typing import Annotated, Sequence
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


from typing import List, Literal

from pydantic import BaseModel, Field

from utils.config import get_config

orchestrator_outputs_tuple = (
    "date_manage",
    "contacts_manage",
    "email_manage",
    "calendar_manage",
    "search_manage",
)

verificaton_outputs_tuple = ("ask_to_user", "error", "continue")


class OrchestratorRouter(BaseModel):
    """Orchestrator answer schema."""

    route_manager: Literal[orchestrator_outputs_tuple] = Field(  # type: ignore
        ...,
        description="The route manager responsible for handling the request.",
    )
    query: str = Field(
        ...,
        description="The query for the manager.",
    )


class OrchestratorRouterList(BaseModel):
    """The managers to route tasks. If no manager needed, use a empty list `[]`."""

    reasoning: str = Field(
        ..., description="Step-by-step reasoning process to give the correct answer"
    )
    managers: List[OrchestratorRouter]


class VerificationSchema(BaseModel):
    """The verification schema for the orchestrator."""

    action: Literal[verificaton_outputs_tuple] = Field(  # type: ignore
        ...,
        description="The action to take for he next step based on the previous steps.",
    )
    detail: str = Field(
        ..., description="Explain in detail why this action was chosen."
    )


class GraphState(TypedDict):
    """The state of the supervisor agents."""

    user_input: str
    user_id: str
    messages: Annotated[list[BaseMessage], add_messages]

    # we'll to manage how update these messages
    supervisors_messages: list[BaseMessage]
    manager_response: list[dict]
    manager_list: list[OrchestratorRouter]


main_model = ChatOpenAI(model=get_config().MAIN_MODEL, temperature=0.0)
mini_model = ChatOpenAI(model=get_config().MINI_MODEL, temperature=0.0)


@runtime_checkable
class WorkerTask(Protocol):
    @property
    def name(self): ...

    @property
    def task(self): ...


async def execute_workers(user_id: str, data: Sequence[WorkerTask], worker):
    """Executes worker tasks asynchronously.

    Args:
        user_id: The user id.
        data: a list of tasks for the worker.
        worker: A worker objects to execute the tasks.

    Returns:
        list: A list of results from the executed worker tasks.
    """
    tasks = [
        worker.ainvoke(
            {
                "workers_messages": HumanMessage(content=task.task),
                "user_id": user_id,
                "account_name": task.name,
                "num_calls": [],
            }
        )
        for task in data
    ]

    results = await asyncio.gather(*tasks)
    return results
