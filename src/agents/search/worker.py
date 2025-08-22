from datetime import datetime
from operator import add
from typing import Annotated, Any, Literal, Sequence

from dotenv import find_dotenv, load_dotenv
from langchain_core.messages import AnyMessage, BaseMessage, SystemMessage
from langchain_core.messages import FunctionMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict

from src.prompts.core import get_prompt_builder
from src.utils.config import get_config
from src.agents.search.tool_google import search_toolset


_ = load_dotenv(find_dotenv())

SEARCH_WORKER_TEMPLATE = get_prompt_builder("src/prompts/config.yaml").build_prompt(
    "src/prompts/google_search_worker.yml"
)[0]


class WorkersState(TypedDict):
    """The state of the worker agents."""

    workers_messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: str
    account_name: str
    num_calls: Annotated[list[str], add]


def tools_condition_worker(
    state: list[AnyMessage] | dict[str, Any] | BaseMessage,
    messages_key: str = "workers_messages",
) -> Literal["tools", "__end__"]:
    """Wrapper to use a message_key different from `message`
    in the pre-built `tools_condition` function.
    """
    return tools_condition(state, messages_key)


def create_google_search_graph(
    tools: list,
    search_worker_template: str = SEARCH_WORKER_TEMPLATE,
    llm=ChatOpenAI(model="gpt-4o-mini", temperature=0.0),
):
    """Creates a Google search graph with customizable parameters.
    
    Args:
        tools (list): The tools to use in the search graph.
        search_worker_template (str): The template for the search worker. Defaults to SEARCH_WORKER_TEMPLATE.
        llm: The language model to use. Defaults to ChatOpenAI(model="gpt-4o-mini", temperature=0.0).
        
    Returns:
        StateGraph: A compiled state graph for Google search operations.
        """
    worker_builder = StateGraph(WorkersState)
    llm_with_tools = llm.bind_tools(search_toolset)

    async def llm_search_node(state: WorkersState):
        """ReAct-style LLM node that optionally calls a tool (SerpAPI)."""

        now = datetime.now(get_config().TIMEZONE)
        datetime_iso = now.isoformat(timespec="seconds")
        day_of_week = now.strftime("%A")
        current_date = f"{day_of_week}, {datetime_iso}"

        # Inject system prompt only if not already present
        if state["workers_messages"][0].type != "system":
            state["workers_messages"].insert(
                0,
                SystemMessage(
                    content=search_worker_template.format(current_date=current_date)
                ),
            )

        response = await llm_with_tools.ainvoke(state["workers_messages"])
        print("🔁 LLM RESPONSE:")
        print(response)

        # # Stop if LLM is hallucinating repeated tool calls
        # if hasattr(response, "tool_calls") and response.tool_calls:
        #     print("🔧 LLM is calling a tool.")
        # else:
        #     print("✅ LLM is done, no tool call.")

        # state["workers_messages"].append(response)
        return {"workers_messages": [response]}

    worker_builder.add_node("llm_with_search_tool", llm_search_node)
    tool_node = ToolNode(tools=tools, messages_key="workers_messages")
    worker_builder.add_node("search_tool_node", tool_node)
    worker_builder.add_conditional_edges(
        "llm_with_search_tool",
        tools_condition_worker,
        {"tools": "search_tool_node", END: END},
    )
    worker_builder.add_edge("search_tool_node", "llm_with_search_tool")
    worker_builder.add_edge(START, "llm_with_search_tool")

    return worker_builder.compile()

# Initialize and export the compiled LangGraph agent
google_search_worker = create_google_search_graph(
    tools=search_toolset,
    search_worker_template=SEARCH_WORKER_TEMPLATE,
)
