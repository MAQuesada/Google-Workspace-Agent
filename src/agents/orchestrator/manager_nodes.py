from typing import Literal
from typing import List

from asgiref.sync import sync_to_async
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from agents.calendar.worker import google_calendar_worker
from agents.contacts.worker import google_contact_worker
from agents.dates.worker import calculate_date
from agents.emails.worker import google_email_worker
from agents.orchestrator.calendar_prompts import (
    CALENDAR_MANAGER_END_PROMPT,
    CALENDAR_MANAGER_SYSTEM_PROMPT,
)
from agents.orchestrator.contacts_prompts import (
    CONTACT_MANAGER_END_PROMPT,
    CONTACT_MANAGER_SYSTEM_PROMPT,
)
from agents.orchestrator.emails_prompts import (
    EMAIL_MANAGER_END_PROMPT,
    EMAIL_MANAGER_SYSTEM_PROMPT,
)
from agents.orchestrator.setup import (
    GraphState,
    execute_workers,
    main_model,
    mini_model,
)
from agents.search.worker import google_search_worker
from google_service.core import get_user_service
from utils.config import get_config
from utils.logger import get_logger

logger = get_logger("orchestrator.managers")


async def calendar_manage_node(
    state: GraphState,
) -> Command[Literal["feedback_synthesizer", "orchestrator"]]:
    """An LLM-based router."""
    logger.info("Calling the calendar manager.")
    supervisors_messages = state["supervisors_messages"]
    manager_response = state["manager_response"]

    accounts = await sync_to_async(get_user_service().list_accounts)(state["user_id"])
    account_dict = {acc.account_email: acc.account_info for acc in accounts}
    google_account_list = [acc.account_email for acc in accounts]

    if len(google_account_list) == 0:
        logger.info("No calendar accounts found.")
        manager_response[-1]["answer"] = "No calendar accounts found."
        return Command(
            goto="orchestrator",
            update={
                "supervisors_messages": [],
                "manager_response": manager_response,
            },
        )

    logger.info(
        "Calendar manager accounts found.", extra={"accounts": google_account_list}
    )

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
    # and avoid go to the feedback synthesizer
    if response.workers == []:
        logger.info("No calendar workers needed.")
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
        manager_response[-1]["answer"] = ai_manager_answer.content
        return Command(
            goto="orchestrator",
            update={
                "supervisors_messages": [],
                "manager_response": manager_response,
            },
        )

    google_respose = [
        worker for worker in response.workers if worker.name in google_account_list
    ]
    logger.info(
        "Executing calendar workers.",
        extra={"workers_to_execute": google_respose},
    )
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
    logger.info("Calendar workers executed successfully.")
    return Command(
        goto="feedback_synthesizer",
        update={"supervisors_messages": supervisors_messages},
    )


def date_manage_node(state: GraphState) -> Command[Literal["orchestrator"]]:
    """Date range extract in `Europe/Paris` timezone"""
    logger.info("Calling the date manager.")
    manager_response = state["manager_response"]

    date_range_str = calculate_date(state["supervisors_messages"][-1].content)
    manager_response[-1]["answer"] = date_range_str
    logger.info("Date range extracted successfully.")
    return Command(
        goto="orchestrator",
        update={
            "supervisors_messages": [],
            "manager_response": manager_response,
        },
    )


async def contacts_manage_node(
    state: GraphState,
) -> Command[Literal["feedback_synthesizer", "orchestrator"]]:
    """An LLM-based router."""
    logger.info("Calling the contacts manager.")
    supervisors_messages = state["supervisors_messages"]
    manager_response = state["manager_response"]

    accounts = await sync_to_async(get_user_service().list_accounts)(state["user_id"])
    account_dict = {acc.account_email: acc.account_info for acc in accounts}
    google_account_list = [acc.account_email for acc in accounts]

    if len(google_account_list) == 0:
        logger.info("No contacts accounts found.")
        manager_response[-1]["answer"] = "No contacts accounts found."
        return Command(
            goto="orchestrator",
            update={
                "supervisors_messages": [],
                "manager_response": manager_response,
            },
        )
    logger.info(
        "Contacts manager accounts found.", extra={"accounts": google_account_list}
    )

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
    # and avoid go to the feedback synthesizer
    if response.workers == []:
        logger.info("No contacts workers needed.")
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
        manager_response[-1]["answer"] = ai_manager_answer.content
        return Command(
            goto="orchestrator",
            update={
                "supervisors_messages": [],
                "manager_response": manager_response,
            },
        )

    google_respose = [
        worker for worker in response.workers if worker.name in google_account_list
    ]
    logger.info(
        "Executing contacts workers.",
        extra={"workers_to_execute": google_respose},
    )
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
    logger.info("Contacts workers executed successfully.")
    return Command(
        goto="feedback_synthesizer",
        update={"supervisors_messages": supervisors_messages},
    )


async def email_manage_node(
    state: GraphState,
) -> Command[Literal["feedback_synthesizer", "orchestrator"]]:
    """An LLM-based router for email management."""

    logger.info("Calling the email manager.")
    supervisors_messages = state["supervisors_messages"]
    manager_response = state["manager_response"]

    accounts = await sync_to_async(get_user_service().list_accounts)(state["user_id"])
    account_dict = {acc.account_email: acc.account_info for acc in accounts}
    google_account_list = [acc.account_email for acc in accounts]

    if len(google_account_list) == 0:
        logger.info("No email accounts found.")
        manager_response[-1]["answer"] = "No email accounts found."
        return Command(
            goto="orchestrator",
            update={
                "supervisors_messages": [],
                "manager_response": manager_response,
            },
        )

    logger.info(
        "Email manager accounts found.", extra={"accounts": google_account_list}
    )

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
        logger.info("No email workers needed.")
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
        manager_response[-1]["answer"] = ai_manager_answer.content
        return Command(
            goto="orchestrator",
            update={
                "supervisors_messages": [],
                "manager_response": manager_response,
            },
        )

    google_response = [
        worker for worker in response.workers if worker.name in google_account_list
    ]
    logger.info(
        "Executing email workers.",
        extra={"workers_to_execute": google_response},
    )
    google_results = await execute_workers(
        state["user_id"], google_response, google_email_worker
    )

    for i, result in enumerate(google_results):
        worker = google_response[i]
        supervisors_messages += [
            AIMessage(content=worker.task, name=worker.name),
            AIMessage(content=result["workers_messages"][-1].content, name=worker.name),
        ]

    logger.info("Email workers executed successfully.")
    return Command(
        goto="feedback_synthesizer",
        update={"supervisors_messages": supervisors_messages},
    )


async def search_manage_node(
    state: GraphState,
) -> Command[Literal["orchestrator"]]:
    """
    Stateless search manager:
    - Receives query/task from supervisors_messages[-1]
    - Invokes search worker
    - Attaches answer to manager_response and returns to orchestrator
    """
    logger.info("Calling the search manager.")
    manager_response = state["manager_response"]
    task = state["supervisors_messages"][-1].content

    result = await google_search_worker.ainvoke(
        {
            "workers_messages": [HumanMessage(content=task)],
            "user_id": state["user_id"],
            "num_calls": [],
        }
    )
    manager_response[-1]["answer"] = result["workers_messages"][-1].content
    logger.info("Search manager executed successfully.")
    return Command(
        goto="orchestrator",
        update={
            "supervisors_messages": [],
            "manager_response": manager_response,
        },
    )
