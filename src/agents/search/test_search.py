# src/agents/google_search/test_google_search.py

from src.agents.search.worker import google_search_worker
from langchain_core.messages import HumanMessage
import asyncio

# Create test input
query = "What are the differences between workflows and agents?"

# Simulate orchestrator-style initial state
initial_state = {
    "workers_messages": [HumanMessage(content=query)],
    "user_id": "test_user",
    "account_name": "test_account",
    "num_calls": ["1"],
}

# Run the graph
async def test_google_search():
    print("Running Google Search agent...\n")
    final_state = await google_search_worker.ainvoke(initial_state, config={'recursion_limit': 50})
    final_message = final_state["workers_messages"][-1]

    print("Final LLM Response:\n")
    print(final_message.content)

# Run async test
if __name__ == "__main__":
    asyncio.run(test_google_search())
