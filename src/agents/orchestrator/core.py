from langgraph.graph import StateGraph
from langgraph.graph import START
from agents.orchestrator.setup import (
    GraphState,
)
from agents.orchestrator.graph import (
    orchestrator_input_node,
    orchestrator_output_node,
    orchestrator_node,
    feedback_synthesizer_node,
)
from agents.orchestrator.manager_nodes import (
    email_manage_node,
    calendar_manage_node,
    contacts_manage_node,
    date_manage_node,
    search_manage_node,
)
from agents.utils import create_checkpointer
from utils.exceptions import OrchestratorInitializationError
from utils.logger import get_logger

logger = get_logger("orchestrator.core")

# build the graph
try:
    orchestrator_builder = StateGraph(GraphState)
    orchestrator_builder.add_node("orchestrator_input", orchestrator_input_node)
    orchestrator_builder.add_node("orchestrator_output", orchestrator_output_node)
    orchestrator_builder.add_node("orchestrator", orchestrator_node)
    orchestrator_builder.add_node("date_manage", date_manage_node)
    orchestrator_builder.add_node("calendar_manage", calendar_manage_node)
    orchestrator_builder.add_node("email_manage", email_manage_node)
    orchestrator_builder.add_node("contacts_manage", contacts_manage_node)
    orchestrator_builder.add_node("search_manage", search_manage_node)
    orchestrator_builder.add_node("feedback_synthesizer", feedback_synthesizer_node)
    orchestrator_builder.add_edge(START, "orchestrator_input")

    # Use the factory function to create the appropriate checkpointer
    checkpointer = create_checkpointer()
    orchestrator_graph = orchestrator_builder.compile(checkpointer=checkpointer)
except Exception as e:
    logger.exception("Error compiling orchestrator graph.")
    raise OrchestratorInitializationError() from e
