from typing import Literal, Any
from datetime import datetime

from langchain_core.messages import SystemMessage, AnyMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel
from dotenv import load_dotenv, find_dotenv

from agents.setup import WorkersState
from agents.emails.tools import google_emails_toolset
from utils.config import get_config
from prompts.core import get_prompt_builder

_ = load_dotenv(find_dotenv())

EMAIL_WORKER_TEMPLATE = get_prompt_builder("src/prompts/config.yaml").build_prompt(
    "src/prompts/email_worker.yml"
)[0]


def tools_condition_worker(
    state: list[AnyMessage] | dict[str, Any] | BaseModel,
    messages_key: str = "workers_messages",
) -> Literal["tools", "__end__"]:
    """Wrapper to use a message_key different from `message` in tools_condition."""
    return tools_condition(state, messages_key)


def create_email_graph(
    tools: list,
    email_worker_template: str = EMAIL_WORKER_TEMPLATE,
    llm=ChatOpenAI(model=get_config().MAIN_MODEL, temperature=0.0),
):
    """
    Creates an email graph with customizable parameters.

    Args:
        tools (list): The tools to use in the email graph.
        email_worker_template (str): The template for the email worker.
        llm: The language model to use.

    Returns:
        StateGraph: A compiled state graph for email operations.
    """
    worker_builder = StateGraph(WorkersState)
    llm_with_tools = llm.bind_tools(tools)

    async def custom_llm_with_email_tools(state: WorkersState):
        """Generate an AIMessage that may include a tool-call to be sent."""
        now = datetime.now(get_config().TIMEZONE)
        datetime_iso = now.isoformat(timespec="seconds")
        dayweek = now.strftime("%A")
        current_date = f"{dayweek}, {datetime_iso}"

        if state["workers_messages"][0].type != "system":
            state["workers_messages"].insert(  # type: ignore
                0,
                SystemMessage(
                    content=email_worker_template.format(
                        current_date=current_date,
                        email_info=state["account_name"],
                        display_items=get_config().MAX_NUM_DISPLAY_ITEMS,
                    )
                ),
            )
        response = await llm_with_tools.ainvoke(state["workers_messages"])
        return {"workers_messages": [response]}

    worker_builder.add_node("llm_with_email_tools", custom_llm_with_email_tools)
    tool_node = ToolNode(tools=tools, messages_key="workers_messages")
    worker_builder.add_node("email_tools", tool_node)
    worker_builder.add_conditional_edges(
        "llm_with_email_tools",
        tools_condition_worker,
        {"tools": "email_tools", END: END},
    )
    worker_builder.add_edge("email_tools", "llm_with_email_tools")
    worker_builder.add_edge(START, "llm_with_email_tools")

    return worker_builder.compile()


google_email_worker = create_email_graph(
    email_worker_template=EMAIL_WORKER_TEMPLATE, tools=google_emails_toolset
)
