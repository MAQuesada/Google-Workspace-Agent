from dotenv import find_dotenv, load_dotenv
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from agents.contacts.tools_google import contacts_toolset as contacts_toolset_google
from agents.setup import WorkersState, tools_condition_worker
from prompts.core import get_prompt_builder
from utils.config import get_config

_ = load_dotenv(find_dotenv())

CONTACTS_WORKER_TEMPLATE = get_prompt_builder("src/prompts/config.yaml").build_prompt(
    "src/prompts/contacts_worker.yml"
)[0]


def create_contacts_graph(
    tools: list,
    contacts_worker_template: str = CONTACTS_WORKER_TEMPLATE,
    llm=ChatOpenAI(model=get_config().MAIN_MODEL, temperature=0.0),
):
    """
    Creates a contacts graph with customizable parameters.

    Args:
        tools (list): The tools to use in the calendar graph.
        calendar_worker_template (str): The template for the calendar worker. Defaults to CALENDAR_WORKER_TEMPLATE.
        llm : The language model to use. Defaults to ChatOpenAI(model="gpt-4o-mini", temperature=0.0).

    Returns:
        StateGraph: A compiled state graph for calendar operations.
    """
    worker_builder = StateGraph(WorkersState)

    llm_with_tools = llm.bind_tools(tools)

    async def custom_llm_with_contact_tools(state: WorkersState):
        """Generate an AIMessage that may include a tool-call to be sent."""

        if state["workers_messages"][0].type != "system":
            state["workers_messages"].insert(  # type: ignore
                0,
                SystemMessage(
                    content=contacts_worker_template.format(
                        contact_info=state["account_name"]
                    )
                ),
            )
        response = await llm_with_tools.ainvoke(state["workers_messages"])
        return {"workers_messages": [response]}

    worker_builder.add_node("llm_with_contact_tools", custom_llm_with_contact_tools)
    tool_node = ToolNode(tools=tools, messages_key="workers_messages")
    worker_builder.add_node("contact_tools", tool_node)
    worker_builder.add_conditional_edges(
        "llm_with_contact_tools",
        tools_condition_worker,
        {"tools": "contact_tools", END: END},
    )
    # Any time a tool is called, we return to the chatbot to decide the next step
    worker_builder.add_edge("contact_tools", "llm_with_contact_tools")
    worker_builder.add_edge(START, "llm_with_contact_tools")

    return worker_builder.compile()


google_contact_worker = create_contacts_graph(
    contacts_worker_template=CONTACTS_WORKER_TEMPLATE, tools=contacts_toolset_google
)
