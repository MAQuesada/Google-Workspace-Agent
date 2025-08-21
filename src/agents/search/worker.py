from datetime import datetime
from operator import add
from typing import Annotated, Any, Literal, Sequence

from dotenv import find_dotenv, load_dotenv
from langchain_core.messages import AnyMessage, BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict

from prompts.core import get_prompt_builder
from utils.config import get_config
from agents.search.tool_google import search_toolset

# Load environment variables
_ = load_dotenv(find_dotenv())

# Build prompt from YAML
SEARCH_WORKER_TEMPLATE = get_prompt_builder("src/prompts/config.yaml").build_prompt(
    "src/prompts/google_search_worker.yml"
)[0]


# Define shared state structure (same as calendar agent)
class WorkersState(TypedDict):
    workers_messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: str
    account_name: str
    num_calls: Annotated[list[str], add]


# Wrapper to reuse prebuilt tools_condition with different key
def tools_condition_worker(
    state: list[AnyMessage] | dict[str, Any] | BaseMessage,
    messages_key: str = "workers_messages",
) -> Literal["tools", "__end__"]:
    return tools_condition(state, messages_key)


# Build LangGraph with LLM + ToolNode
def create_google_search_graph(
    tools: list,
    search_worker_template: str = SEARCH_WORKER_TEMPLATE,
    llm=ChatOpenAI(model="gpt-4o-mini", temperature=0.0),
):
    worker_builder = StateGraph(WorkersState)
    llm_with_tools = llm.bind_tools(search_toolset)

    async def llm_search_node(state: WorkersState):
        """ReAct-style LLM node that optionally calls a tool (SerpAPI)."""

        now = datetime.now(get_config().TIMEZONE)
        datetime_iso = now.isoformat(timespec="seconds")
        day_of_week = now.strftime("%A")
        current_date = f"{day_of_week}, {datetime_iso}"

        # Inject system prompt only if not already present
        if (
            not state["workers_messages"]
            or state["workers_messages"][0].type != "system"
        ):
            state["workers_messages"].insert(  # type: ignore
                0,
                SystemMessage(
                    content=search_worker_template.format(current_date=current_date)
                ),
            )

        response = await llm_with_tools.ainvoke(state["workers_messages"])
        print("🔁 LLM RESPONSE:")
        print(response)

        # Stop if LLM is hallucinating repeated tool calls
        if hasattr(response, "tool_calls") and response.tool_calls:
            print("🔧 LLM is calling a tool.")
        else:
            print("✅ LLM is done, no tool call.")

        state["workers_messages"].append(response)  # type: ignore
        return {"workers_messages": state["workers_messages"]}

    worker_builder.add_node("llm_with_search_tool", llm_search_node)
    worker_builder.add_node(
        "search_tool_node", ToolNode(tools=tools, messages_key="workers_messages")
    )

    worker_builder.add_conditional_edges(
        "llm_with_search_tool",
        tools_condition_worker,
        {"tools": "search_tool_node", "__end__": END},
    )
    worker_builder.add_edge("search_tool_node", "llm_with_search_tool")
    worker_builder.add_edge(START, "llm_with_search_tool")

    return worker_builder.compile()


# Initialize and export the compiled LangGraph agent
google_search_worker = create_google_search_graph(
    tools=search_toolset,
    search_worker_template=SEARCH_WORKER_TEMPLATE,
)
