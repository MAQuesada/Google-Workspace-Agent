from psycopg_pool import ConnectionPool
import os
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
)
from agents.utils import PostgresSaverCustom

# build the graph
orchestrator_builder = StateGraph(GraphState)


orchestrator_builder.add_node("orchestrator_input", orchestrator_input_node)
orchestrator_builder.add_node("orchestrator_output", orchestrator_output_node)
orchestrator_builder.add_node("orchestrator", orchestrator_node)
orchestrator_builder.add_node("date_manage", date_manage_node)
orchestrator_builder.add_node("calendar_manage", calendar_manage_node)
orchestrator_builder.add_node("email_manage", email_manage_node)
orchestrator_builder.add_node("contacts_manage", contacts_manage_node)
orchestrator_builder.add_node("feedback_synthesizer", feedback_synthesizer_node)
orchestrator_builder.add_edge(START, "orchestrator_input")


DB_URI = os.environ.get("POSTGRES_DB_URI")

# conservatively set the pool size to 3
pool = ConnectionPool(
    conninfo=DB_URI,
    min_size=3,
    max_size=3,
    max_lifetime=900,
    max_waiting=12,
    max_idle=180,
    kwargs={
        "autocommit": True,
        "prepare_threshold": 0,
    },
)
checkpointer = PostgresSaverCustom(pool)

checkpointer.setup()
orchestrator_graph = orchestrator_builder.compile(checkpointer=checkpointer)
