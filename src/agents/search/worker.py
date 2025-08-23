from dotenv import find_dotenv, load_dotenv
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode

from agents.setup import WorkersState, tools_condition_worker
from prompts.core import get_prompt_builder
from utils.config import get_config
from agents.search.tool_google import search_toolset

# Load environment variables
_ = load_dotenv(find_dotenv())

# Build prompt from YAML
SEARCH_WORKER_TEMPLATE = get_prompt_builder("src/prompts/config.yaml").build_prompt("src/prompts/google_search_worker.yml")[0]


# Build LangGraph with LLM + ToolNode
def create_google_search_graph(
    tools: list,
    search_worker_template: str = SEARCH_WORKER_TEMPLATE,
    llm=ChatOpenAI(model=get_config().MAIN_MODEL, temperature=0.0),
):
    worker_builder = StateGraph(WorkersState)
    llm_with_tools = llm.bind_tools(tools)

    async def llm_search_node(state: WorkersState):
        """ReAct-style LLM node that optionally calls a tool (SerpAPI)."""

        # Inject system prompt only if not already present
        if (
            not state["workers_messages"]
            or state["workers_messages"][0].type != "system"
        ):
            state["workers_messages"].insert(  # type: ignore
                0, SystemMessage(content=search_worker_template)
            )

        response = await llm_with_tools.ainvoke(state["workers_messages"])

        return {"workers_messages": response}

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
