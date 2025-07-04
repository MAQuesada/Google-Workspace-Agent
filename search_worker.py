from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from serpapi import GoogleSearch
from typing import TypedDict, List
from dotenv import load_dotenv
import os
import re

from prompts.core import get_prompt_builder

load_dotenv()
SERPAPI_API_KEY = os.getenv("serp_api_key")
OPENAI_API_KEY = os.getenv("openai_api_key")

SEARCH_PROMPT = get_prompt_builder('./prompts/config.yaml').build_prompt_template("./prompts/google_search_worker.yml")
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# -------------------------
# Tool: Google Search via SerpAPI
# -------------------------
@tool
def google_search_tool(query: str) -> dict:
    """Search Google and return the top 3 clean text results."""
    search = GoogleSearch({
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "num": 3
    })
    results = search.get_dict()
    output = []

    for result in results.get("organic_results", [])[:3]:
        content = result.get("snippet") or ""
        clean_text = re.sub(r'<.*?>', '', content)
        output.append({
            "url": result.get("link", ""),
            "content": clean_text.strip()
        })

    return {
        "answer": f"Here are the top 3 results for: {query}",
        "results": output
    }

# -------------------------
# Typed Structures
# -------------------------
class SearchResult(TypedDict):
    url: str
    content: str

class SearchOutput(TypedDict):
    answer: str
    results: List[SearchResult]

class AgentState(TypedDict):
    input: str
    results: SearchOutput
    final_answer: str

# -------------------------
# Node 1: Google Search
# -------------------------
def search_and_present(query):
    llm_input = SEARCH_PROMPT.format(query=query)
    llm_response = llm.invoke(llm_input)
    print("\n--- Final Answer ---")
    print(llm_response.content)

# -------------------------
# Build LangGraph
# -------------------------
builder = StateGraph(AgentState)
builder.add_node("search and generate", RunnableLambda(search_and_present))
builder.set_entry_point("search and generate")
builder.add_edge("search and genrate", END)
google_search_agent = builder.compile()



# -------------------------
# Run Agent
# -------------------------
if __name__ == "__main__":

    query = input("Input search query : ")
    search_and_present(query)
   

    
