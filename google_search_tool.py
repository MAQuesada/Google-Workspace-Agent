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

load_dotenv()
SERPAPI_API_KEY = os.getenv("serp_api_key")
OPENAI_API_KEY = os.getenv("openai_api_key")

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
def call_google_search(state: AgentState) -> dict:
    query = state["input"]
    try:
        results = google_search_tool.invoke(query)
    except Exception as e:
        results = {
            "answer": f"An error occurred: {str(e)}",
            "results": []
        }
    return {"results": results}

# -------------------------
# Node 2: Use LLM to Generate Final Response
# -------------------------
llm = ChatOpenAI(model="gpt-4o", temperature=0)

def llm_response(state: AgentState) -> dict:
    query = state["input"]
    results = state["results"]["results"]

    context_text = "\n\n".join(
        [f"{i+1}. {r['content']} (Source: {r['url']})" for i, r in enumerate(results)]
    )

    prompt = f"""You are a helpful assistant. Based on the following search results, answer the user query:
Query: "{query}"

Search Results:
{context_text}

Provide a clear, concise, and helpful answer based only on these results. Do not hallucinate.
"""

    response = llm.invoke([HumanMessage(content=prompt)])
    return {"final_answer": response.content}

# -------------------------
# Build LangGraph
# -------------------------
builder = StateGraph(AgentState)
builder.add_node("search", RunnableLambda(call_google_search))
builder.add_node("generate_response", RunnableLambda(llm_response))
builder.set_entry_point("search")
builder.add_edge("search", "generate_response")
builder.add_edge("generate_response", END)
google_search_agent = builder.compile()

# -------------------------
# Run Agent
# -------------------------
if __name__ == "__main__":
    import asyncio

    query = input("Enter search query: ")
    result = asyncio.run(google_search_agent.ainvoke({"input": query}))
    
    print("\n--- Final Answer ---\n")
    print(result["final_answer"])
    
    print("\n--- Sources ---")
    for r in result["results"]["results"]:
        print(f"- {r['url']}")
