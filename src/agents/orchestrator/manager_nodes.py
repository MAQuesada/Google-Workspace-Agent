from agents.dates.worker import calculate_date
from typing import Literal
from typing import List

from asgiref.sync import sync_to_async
from langchain_core.messages import SystemMessage, AIMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from agents.calendar.worker import google_calendar_worker
from agents.contacts.worker import google_contact_worker
from agents.emails.worker import google_email_worker
from agents.search.worker import google_search_worker
from agents.orchestrator.setup import (
    GraphState,
    main_model,
    mini_model,
    execute_workers,
)

from agents.orchestrator.calendar_prompts import (
    CALENDAR_MANAGER_END_PROMPT,
    CALENDAR_MANAGER_SYSTEM_PROMPT,
)
from agents.orchestrator.contacts_prompts import (
    CONTACT_MANAGER_SYSTEM_PROMPT,
    CONTACT_MANAGER_END_PROMPT,
)

from agents.orchestrator.emails_prompts import (
    EMAIL_MANAGER_END_PROMPT,
    EMAIL_MANAGER_SYSTEM_PROMPT,
)

from agents.orchestrator.search_prompts import (
    SEARCH_MANAGER_SYSTEM_PROMPT,
    SEARCH_MANAGER_END_PROMPT,   
)


from google_service.core import get_user_service
from utils.config import get_config


async def calendar_manage_node(
    state: GraphState,
) -> Command[Literal["feedback_synthesizer"]]:
    """An LLM-based router."""

    supervisors_messages = state["supervisors_messages"]

    accounts = await sync_to_async(get_user_service().list_accounts)(state["user_id"])

    account_dict = {acc.account_email: acc.account_info for acc in accounts}
    google_account_list = [acc.account_email for acc in accounts]

    class WorkerRouter(BaseModel):
        name: Literal[tuple(account_dict.keys())] = Field(  # type: ignore
            description="The calendar worker to be called to execute the task."
        )
        task: str = Field(
            description="A concise description of the task to perform for the worker."
        )

    class WorkerRouterList(BaseModel):
        """Worker to route to tasks. If no workers needed, use a empty list `[]`."""

        workers: List[WorkerRouter]

    system_mess = [
        SystemMessage(
            content=CALENDAR_MANAGER_SYSTEM_PROMPT.format(
                calendar_workers_info_dict=account_dict
            )
        )
    ]
    messages = system_mess + supervisors_messages

    response: WorkerRouterList = main_model.with_structured_output(
        WorkerRouterList
    ).invoke(messages)

    # in this case the manager must elaborate an answer
    # to avoid go to the feedback synthesizer with an empty ai asnwers
    if response.workers == []:
        ai_manager_answer = mini_model.invoke(
            [
                SystemMessage(
                    content=CALENDAR_MANAGER_END_PROMPT.format(
                        calendar_workers_info_dict=account_dict
                    )
                )
            ]
            + supervisors_messages
        )
        # ensure the ai answer is in the 3rd position
        supervisors_messages += supervisors_messages + [ai_manager_answer]
        return Command(
            goto="feedback_synthesizer",
            update={"supervisors_messages": supervisors_messages},
        )

    google_respose = [
        worker for worker in response.workers if worker.name in google_account_list
    ]

    google_results = await execute_workers(
        state["user_id"], google_respose, google_calendar_worker
    )

    for i, result in enumerate(google_results):
        worker = google_respose[i]
        supervisors_messages += [
            AIMessage(content=worker.task, name=worker.name),
        ]
        supervisors_messages += [
            AIMessage(content=result["workers_messages"][-1].content, name=worker.name)
        ]

    return Command(
        goto="feedback_synthesizer",
        update={"supervisors_messages": supervisors_messages},
    )


def date_manage_node(state: GraphState) -> Command[Literal["orchestrator"]]:
    """Date range extract in `Europe/Paris` timezone"""
    manager_response = state["manager_response"]

    date_range_str = calculate_date(state["supervisors_messages"][-1].content)
    manager_response[-1]["answer"] = date_range_str

    return Command(
        goto="orchestrator",
        update={
            "supervisors_messages": [],
            "manager_response": manager_response,
        },
    )


async def contacts_manage_node(
    state: GraphState,
) -> Command[Literal["feedback_synthesizer"]]:
    """An LLM-based router."""

    supervisors_messages = state["supervisors_messages"]

    accounts = await sync_to_async(get_user_service().list_accounts)(state["user_id"])

    account_dict = {acc.account_email: acc.account_info for acc in accounts}
    google_account_list = [acc.account_email for acc in accounts]

    class WorkerRouter(BaseModel):
        name: Literal[tuple(account_dict.keys())] = Field(  # type: ignore
            description="The contact worker to be called to execute the task."
        )
        task: str = Field(
            description="A concise description of the task to perform for the worker."
        )

    class WorkerRouterList(BaseModel):
        """Worker to route to tasks. If no workers needed, use a empty list `[]`."""

        workers: List[WorkerRouter]

    system_mess = [
        SystemMessage(
            content=CONTACT_MANAGER_SYSTEM_PROMPT.format(
                contact_workers_info_dict=account_dict
            )
        )
    ]
    messages = system_mess + supervisors_messages

    response: WorkerRouterList = mini_model.with_structured_output(
        WorkerRouterList
    ).invoke(messages)

    # in this case the manager must elaborate an answer
    # to avoid go to the feedback synthesizer with an empty ai asnwers
    if response.workers == []:
        ai_manager_answer = mini_model.invoke(
            [
                SystemMessage(
                    content=CONTACT_MANAGER_END_PROMPT.format(
                        contact_workers_info_dict=account_dict
                    )
                )
            ]
            + supervisors_messages
        )
        # ensure the ai answer is in an odd position
        supervisors_messages += supervisors_messages + [ai_manager_answer]
        return Command(
            goto="feedback_synthesizer",
            update={"supervisors_messages": supervisors_messages},
        )

    google_respose = [
        worker for worker in response.workers if worker.name in google_account_list
    ]

    google_results = await execute_workers(
        state["user_id"], google_respose, google_contact_worker
    )

    for i, result in enumerate(google_results):
        worker = google_respose[i]
        supervisors_messages += [
            AIMessage(content=worker.task, name=worker.name),
        ]
        supervisors_messages += [
            AIMessage(content=result["workers_messages"][-1].content, name=worker.name)
        ]

    return Command(
        goto="feedback_synthesizer",
        update={"supervisors_messages": supervisors_messages},
    )


async def email_manage_node(
    state: GraphState,
) -> Command[Literal["feedback_synthesizer"]]:
    """An LLM-based router for email management."""
    supervisors_messages = state["supervisors_messages"]

    # Obtener cuentas de Google y Microsoft
    accounts = await sync_to_async(get_user_service().list_accounts)(state["user_id"])
    account_dict = {acc.account_email: acc.account_info for acc in accounts}
    google_account_list = [acc.account_email for acc in accounts]

    class WorkerRouter(BaseModel):
        name: Literal[tuple(account_dict.keys())] = Field(  # type: ignore
            description="The email worker to be called to execute the task."
        )
        task: str = Field(
            description="A concise description of the task to perform for the worker."
        )

    class WorkerRouterList(BaseModel):
        """Worker to route to tasks. If no workers needed, use an empty list `[]`."""

        workers: List[WorkerRouter]

    system_mess = [
        SystemMessage(
            content=EMAIL_MANAGER_SYSTEM_PROMPT.format(
                email_workers_info_dict=account_dict,
                MAX_NUM_DISPLAY_ITEMS=get_config().MAX_NUM_DISPLAY_ITEMS,
            )
        )
    ]
    messages = system_mess + supervisors_messages

    response: WorkerRouterList = main_model.with_structured_output(
        WorkerRouterList
    ).invoke(messages)

    if response.workers == []:
        ai_manager_answer = mini_model.invoke(
            [
                SystemMessage(
                    content=EMAIL_MANAGER_END_PROMPT.format(
                        email_workers_info_dict=account_dict,
                        MAX_NUM_DISPLAY_ITEMS=get_config().MAX_NUM_DISPLAY_ITEMS,
                    )
                )
            ]
            + supervisors_messages
        )
        supervisors_messages += [ai_manager_answer]
        return Command(
            goto="feedback_synthesizer",
            update={"supervisors_messages": supervisors_messages},
        )

    google_response = [
        worker for worker in response.workers if worker.name in google_account_list
    ]

    google_results = await execute_workers(
        state["user_id"], google_response, google_email_worker
    )

    for i, result in enumerate(google_results):
        worker = google_response[i]
        supervisors_messages += [
            AIMessage(content=worker.task, name=worker.name),
            AIMessage(content=result["workers_messages"][-1].content, name=worker.name),
        ]

    return Command(
        goto="feedback_synthesizer",
        update={"supervisors_messages": supervisors_messages},
    )

async def search_manage_node(
    state: GraphState,
) -> Command[Literal["feedback_synthesizer"]]:
    """An LLM-based router for search management."""
    supervisors_messages = state["supervisors_messages"]

    # For search, we don't need user accounts, but we create a simple worker info dict
    search_workers_info_dict = {"google_search": "Web search using Google"}

    class WorkerRouter(BaseModel):
        name: Literal["google_search"] = Field(
            description="The search worker to be called to execute the task."
        )
        task: str = Field(
            description="A detailed description of the search task to perform."
        )

    class WorkerRouterList(BaseModel):
        """Search worker to route to tasks. If no workers needed, use an empty list `[]`."""

        workers: List[WorkerRouter]

    system_mess = [
        SystemMessage(
            content=SEARCH_MANAGER_SYSTEM_PROMPT.format(
                search_workers_info_dict=search_workers_info_dict
            )
        )
    ]
    messages = system_mess + supervisors_messages

    response: WorkerRouterList = main_model.with_structured_output(
        WorkerRouterList
    ).invoke(messages)

    if response.workers == []:
        ai_manager_answer = mini_model.invoke(
            [
                SystemMessage(
                    content=SEARCH_MANAGER_END_PROMPT.format(
                        search_workers_info_dict=search_workers_info_dict
                    )
                )
            ]
            + supervisors_messages
        )
        supervisors_messages += [ai_manager_answer]
        return Command(
            goto="feedback_synthesizer",
            update={"supervisors_messages": supervisors_messages},
        )

    # Execute search workers
    search_results = []
    for worker in response.workers:
        result = await google_search_worker.ainvoke({
            "workers_messages": [HumanMessage(content=worker.task)],
            "user_id": state["user_id"],
            "num_calls": [],
        })
        search_results.append(result)

    for i, result in enumerate(search_results):
        worker = response.workers[i]
        supervisors_messages += [
            AIMessage(content=worker.task, name=worker.name),
            AIMessage(content=result["workers_messages"][-1].content, name=worker.name),
        ]

    return Command(
        goto="feedback_synthesizer",
        update={"supervisors_messages": supervisors_messages},
    )

