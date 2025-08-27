from typing import Literal

from asgiref.sync import sync_to_async
from langchain_core.messages import (
    trim_messages,
    HumanMessage,
    SystemMessage,
    AIMessage,
)
from langgraph.constants import END
from langgraph.types import Command

from agents.orchestrator.calendar_prompts import FEEDBACK_CALENDAR_MANAGER_PROMPT
from agents.orchestrator.contacts_prompts import FEEDBACK_CONTACT_MANAGER_PROMPT
from agents.orchestrator.emails_prompts import FEEDBACK_EMAIL_MANAGER_PROMPT
from utils.config import get_config


from agents.orchestrator.other_prompts import (
    ENTRY_POINT_TEMPLATE,
    ENTRY_PROMPT_ORCHESTRATOR,
    FINAL_ANSWER_TEMPLATE,
    RESPONSE_PROMPT_ORCHESTRATOR,
    VERIFICATION_PROMPT,
    MANAGER_TEMPLATE,
)
from agents.orchestrator.setup import (
    OrchestratorRouterList,
    orchestrator_outputs_tuple,
    VerificationSchema,
    verificaton_outputs_tuple,
    GraphState,
    main_model,
    mini_model,
)
from google_service.core import get_user_service
from utils.logger import get_logger

logger = get_logger("orchestrator.graph")

trimmer = trim_messages(
    max_tokens=7,  # to keep the last 3 interactions messages
    strategy="last",
    token_counter=len,
    include_system=True,
    start_on="human",
    end_on=("human",),
)


async def orchestrator_input_node(
    state: GraphState,
) -> Command[Literal["orchestrator"]]:
    """An orchestrator node. Entry point of the graph."""
    logger.info("Calling the orchestrator input node.")
    # we must create the user message
    if len(state["messages"]) == 0 or state["messages"][-1].type == "ai":
        state["messages"].append(
            HumanMessage(
                content=ENTRY_POINT_TEMPLATE.format(
                    **{"user_request": state["user_input"]}
                )
            )
        )
    accounts = await sync_to_async(get_user_service().list_accounts)(state["user_id"])
    account_dict = {acc.account_email: acc.account_info for acc in accounts}
    logger.info("Accounts found.", extra={"accounts": account_dict})

    user = await sync_to_async(get_user_service().load_user)(state["user_id"])

    if user is None:
        logger.error("User not found.", extra={"user_id": state["user_id"]})
        return Command(
            goto="orchestrator",
            update={"manager_list": [], "manager_response": []},
        )

    system_mes = [
        SystemMessage(
            content=ENTRY_PROMPT_ORCHESTRATOR.format(
                contacts_worker_info_list=account_dict,
                email_worker_summary_list=account_dict,
                calendar_worker_summary_list=account_dict,
                documents_worker_summary_list=account_dict,
                user_name=user.username,
            )
        )
    ]

    messages = system_mes + trimmer.invoke(state["messages"])

    response: OrchestratorRouterList = main_model.with_structured_output(
        OrchestratorRouterList
    ).invoke(messages)

    logger.info(
        "Orchestrator input node executed successfully.",
        extra={"managers_list": [m.route_manager for m in response.managers]},
    )
    return Command(
        goto="orchestrator",
        update={"manager_list": response.managers, "manager_response": []},
    )


async def orchestrator_output_node(
    state: GraphState,
) -> Command[Literal[END]]:
    """An orchestrator node. Output point of the graph."""

    logger.info("Calling the orchestrator output node.")
    # update the user message with the manager response
    state["messages"][-1] = HumanMessage(
        content=FINAL_ANSWER_TEMPLATE.format(
            **{
                "user_request": state["user_input"],
                "manager_response": state.get("manager_response") or "NULL",
            }
        )
    )
    accounts = await sync_to_async(get_user_service().list_accounts)(state["user_id"])
    account_dict = {acc.account_email: acc.account_info for acc in accounts}
    logger.info("Accounts found.", extra={"accounts": account_dict})
    user = await sync_to_async(get_user_service().load_user)(state["user_id"])
    if user is None:
        logger.error("User not found.", extra={"user_id": state["user_id"]})
        return Command(
            goto=END,
            update={
                "messages": [
                    AIMessage(
                        content="The user is not registered. Please register to use the service."
                    )
                ],
            },
        )

    system_mes = [
        SystemMessage(
            content=RESPONSE_PROMPT_ORCHESTRATOR.format(
                contacts_worker_info_list=account_dict,
                email_worker_summary_list=account_dict,
                calendar_worker_summary_list=account_dict,
                documents_worker_summary_list=account_dict,
                associated_account_list=account_dict,
                user_name=user.username,
            )
        )
    ]

    # trimmer here, to use just the last 3 user interactions
    messages = system_mes + trimmer.invoke(state["messages"])

    ai_response = ""
    async for chunk in main_model.astream(messages):
        ai_response += chunk.content

    logger.info("Orchestrator output node executed successfully.")
    return Command(
        goto=END,
        update={
            "messages": [AIMessage(content=ai_response)],
        },
    )


async def orchestrator_node(
    state: GraphState,
) -> Command[Literal[orchestrator_outputs_tuple + ("orchestrator_output",)]]:
    """An orchestrator node. Execution point of managers in the graph."""
    logger.info("Calling the orchestrator/executor node.")

    if state["manager_list"] == []:
        logger.info("No more managers to route.")
        return Command(goto="orchestrator_output")

    manager_list = state.get("manager_list")
    manager_response = state.get("manager_response", [])

    # if data_manager failed: return to make the user's answer
    if (
        len(manager_response) > 0
        and "date_manage" in str(manager_response[-1].get("route_manager"))
        and "error" in str(manager_response[-1].get("answer")).lower()
    ):
        logger.info("Date manager failed. Returning to orchestrator output.")
        return Command(goto="orchestrator_output")

    next_manager = manager_list.pop(0)  # type: ignore

    if len(manager_response) > 0 and next_manager.route_manager != "date_manage":
        logger.info("Calling the verifier step.")
        verification: VerificationSchema = mini_model.with_structured_output(
            VerificationSchema
        ).invoke(
            input=VERIFICATION_PROMPT.format(
                output_action=verificaton_outputs_tuple,
                manager_called=manager_response,
                manager_actual=next_manager,
            )
        )
        if verification.action == "error" or verification.action == "ask_to_user":
            logger.info("Verifier step failed. Returning to orchestrator output.")
            return Command(
                goto="orchestrator_output",
                update={
                    "manager_response": manager_response
                    + [
                        {
                            "route_manager": "verifier",
                            "query": "Is there enough context for the called managers to call the next one?",
                            "answer": verification.detail,
                        }
                    ]
                },
            )
        else:
            logger.info(
                "Verifier step passed. Calling the next manager.",
                extra={"next_manager": next_manager.route_manager},
            )
    logger.info(
        "Calling the next manager.", extra={"next_manager": next_manager.route_manager}
    )
    return Command(
        goto=next_manager.route_manager,
        update={
            "manager_list": manager_list,
            "manager_response": manager_response + [dict(next_manager)],
            # reset the supervisors messages
            "supervisors_messages": [
                HumanMessage(
                    content=MANAGER_TEMPLATE.format(
                        user_request=next_manager.query,
                        manager_response_context=manager_response or "NULL",
                    )
                )
            ],
        },
    )


def feedback_synthesizer_node(state: GraphState) -> Command[Literal["orchestrator"]]:
    """Synthesizes feedback and return to the orchestrator."""

    # state["supervisors_messages"] contains the query from the orchestrator
    orchestrator_query = state["supervisors_messages"][0].content
    manager_response = state["manager_response"]
    agents_chat_history = ""

    logger.info(
        "Calling the feedback synthesizer node.",
        extra={"from_manager": manager_response[-1]["route_manager"]},
    )

    # we just need the agents messages to be able to synthesize the feedback
    # in 0 is the orchestrator query, in 1,3,5...(odd) is the supervisor query
    for i, mess in enumerate(state["supervisors_messages"][2::2]):
        agents_chat_history += f" ### Message {i + 1} - Agent/Account: {mess.name}:\n"
        agents_chat_history += f"```{mess.content}```\n\n"

    agents_chat_history = agents_chat_history[:-2]  # remove the last \n\n

    # Select appropriate feedback prompt based on manager type
    if manager_response[-1]["route_manager"] == "calendar_manage":
        feedback_prompt_template = FEEDBACK_CALENDAR_MANAGER_PROMPT
    elif manager_response[-1]["route_manager"] == "email_manage":
        feedback_prompt_template = FEEDBACK_EMAIL_MANAGER_PROMPT
    elif manager_response[-1]["route_manager"] == "contacts_manage":
        feedback_prompt_template = FEEDBACK_CONTACT_MANAGER_PROMPT

    else:
        logger.error(
            "Invalid manager type.",
            extra={"manager_type": manager_response[-1]["route_manager"]},
        )
        raise ValueError(
            f"Invalid manager type: {manager_response[-1]['route_manager']}"
        )

    ai_response = mini_model.invoke(
        input=feedback_prompt_template.format(
            agents_chat_history=agents_chat_history,
            query=orchestrator_query,
            MAX_NUM_DISPLAY_ITEMS=get_config().MAX_NUM_DISPLAY_ITEMS,
        )
    )

    # set the manager answer to the last orchestrator query
    manager_response[-1]["answer"] = ai_response.content
    logger.info(
        "Feedback synthesizer node executed successfully.",
        extra={"from_manager": manager_response[-1]["route_manager"]},
    )
    return Command(
        goto="orchestrator",
        update={
            "supervisors_messages": [],
            "manager_response": manager_response,
        },
    )
