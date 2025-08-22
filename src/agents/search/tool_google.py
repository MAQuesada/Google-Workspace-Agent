import re
from typing import Annotated, List
from langchain_core.tools import StructuredTool
from serpapi import GoogleSearch
from langgraph.prebuilt import InjectedState
from langchain_core.tools.base import InjectedToolCallId
from pydantic import BaseModel, Field
import os
from dotenv import load_dotenv
from src.agents.utils import limit_calls


load_dotenv()
SERPAPI_API_KEY = os.getenv("SERP_API_KEY")




class GoogleSearchSchema(BaseModel):
    query: str = Field(..., description="The search query to look up on Google.")



@limit_calls(max_calls=10)
def perform_google_search(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    query: str,
) -> dict:
    if not SERPAPI_API_KEY:
     return {
        "answer": "SerpAPI key not found. Please set `serp_api_key` in your .env file.",
        "results": [],
    }
    search = GoogleSearch({
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "num": 3,
    })

    results = search.get_dict()
    output = []

    organic = results.get("organic_results")
    if not organic:
        return {
        "answer": f"No search results found for: {query}",
        "results": []
    }

    for result in organic[:3]:
        content = result.get("snippet") or ""
        clean_text = re.sub(r"<.*?>", "", content)
        output.append({
            "url": result.get("link", ""),
            "content": clean_text.strip()
        })

    return {
        "answer": f"Top 3 search results for: {query}",
        "results": output
    }


google_search_tool = StructuredTool(
    name="google_search_tool",
    description="Uses Google to search for information and returns top 3 results with clean text.",
    args_schema=GoogleSearchSchema,
    func=perform_google_search,
)


search_toolset = [google_search_tool]
