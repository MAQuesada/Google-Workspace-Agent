from datetime import datetime
from operator import add
from typing import Annotated, Any, Literal, Sequence
from dotenv import find_dotenv, load_dotenv
from langchain_core.messages import AnyMessage, BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph
from langgraph.graph import END, START
from langgraph.prebuilt import ToolNode

from src.agents.setup import WorkersState, tools_condition_worker
from prompts.core import get_prompt_builder
from utils.config import get_config
from agents.calendar.tool_google import calendar_toolset_google
from src.prompts.core import get_prompt_builder
from src.utils.config import get_config
from src.agents.calendar.tool_google import calendar_toolset_google

_ = load_dotenv(find_dotenv())

CALENDAR_WORKER_TEMPLATE = get_prompt_builder("src/prompts/config.yaml").build_prompt(
    "src/prompts/calendar_worker.yml"
)[0]


def create_calendar_graph(
    tools: list,
    calendar_worker_template: str = CALENDAR_WORKER_TEMPLATE,
    llm=ChatOpenAI(model=get_config().MAIN_MODEL, temperature=0.0),
):
    """
    Creates a calendar graph with customizable parameters.

    Args:
        tools (list): The tools to use in the calendar graph.
        calendar_worker_template (str): The template for the calendar worker. Defaults to CALENDAR_WORKER_TEMPLATE.
        llm : The language model to use.

    Returns:
        StateGraph: A compiled state graph for calendar operations.
    """
    worker_builder = StateGraph(WorkersState)

    llm_with_tools = llm.bind_tools(tools)

    async def custom_llm_with_calendar_tools(state: WorkersState):
        """Generate an AIMessage that may include a tool-call to be sent."""

        now = datetime.now(get_config().TIMEZONE)
        # Generate ISO 8601 format with seconds
        datetime_iso = now.isoformat(timespec="seconds")
        dayweek = now.strftime("%A")
        current_date = f"{dayweek}, {datetime_iso}"

        if state["workers_messages"][0].type != "system":
            state["workers_messages"].insert(  # type: ignore
                0,
                SystemMessage(
                    content=calendar_worker_template.format(
                        current_date=current_date, calendar_info=state["account_name"]
                    )
                ),
            )
        response = await llm_with_tools.ainvoke(state["workers_messages"])
        return {"workers_messages": [response]}

    worker_builder.add_node("llm_with_calendar_tools", custom_llm_with_calendar_tools)
    tool_node = ToolNode(tools=tools, messages_key="workers_messages")
    worker_builder.add_node("calendar_tools", tool_node)
    worker_builder.add_conditional_edges(
        "llm_with_calendar_tools",
        tools_condition_worker,
        {"tools": "calendar_tools", END: END},
    )
    # Any time a tool is called, we return to the chatbot to decide the next step
    worker_builder.add_edge("calendar_tools", "llm_with_calendar_tools")
    worker_builder.add_edge(START, "llm_with_calendar_tools")

    return worker_builder.compile()


google_calendar_worker = create_calendar_graph(
    calendar_worker_template=CALENDAR_WORKER_TEMPLATE, tools=calendar_toolset_google
)
