import json
import re
import pytest

from agents.search.worker import google_search_worker


from conftest import _extract_final_ai_message_content, _extract_json_block


@pytest.mark.asyncio
async def test_agent_handles_greeting_without_tools():
    """
    Sanity check: a simple greeting should not require a tool call.
    We just verify the worker returns a final assistant message.
    """
    result = await google_search_worker.ainvoke(
        {
            "workers_messages": [
                {"type": "human", "content": "Hi. how you can help me?"}
            ],
        }
    )

    assert "workers_messages" in result
    last = _extract_final_ai_message_content(result)
    assert isinstance(last, str) and len(last) > 0
    # No strict assertion on JSON format here—your worker greets with free text first.


@pytest.mark.asyncio
async def test_agent_search_success(monkeypatch):
    """
    Ask the agent to search for information about agents vs workflows.
    With our search fakes, the tool 'google_search_tool' will be used
    and we should receive a JSON block with the search results.
    """
    # Mock the SerpAPI response
    mock_search_results = {
        "organic_results": [
            {
                "link": "https://langchain-ai.github.io/langgraph/tutorials/workflows/",
                "snippet": "Workflows are systems where LLMs and tools are orchestrated through predefined code paths. Agents, on the other hand, are systems where LLMs dynamically direct their own processes and tools usage, maintaining control over how they accomplish tasks.",
            },
            {
                "link": "https://medium.com/@vipra_singh/ai-agent-workflow-vs-agent-part-5-2026a890a33d",
                "snippet": "Workflows work best for static, repetitive processes, while Agents are ideal for dynamic, multi-step reasoning tasks where adaptability is key.",
            },
            {
                "link": "https://www.louisbouchard.ai/agents-vs-workflows/",
                "snippet": "Agents are systems where LLMs dynamically direct their own processes and tools usage, maintaining control over how they accomplish tasks.",
            },
        ]
    }

    class MockGoogleSearch:
        def __init__(self, params):
            self.params = params

        def get_dict(self):
            return mock_search_results

    # Mock the GoogleSearch class and SERPAPI_API_KEY
    monkeypatch.setattr("agents.search.tool_google.GoogleSearch", MockGoogleSearch)
    monkeypatch.setattr("agents.search.tool_google.SERPAPI_API_KEY", "fake_api_key")

    result = await google_search_worker.ainvoke(
        {
            "workers_messages": [
                {
                    "type": "human",
                    "content": "Tell me the difference between agents and workflows",
                }
            ],
        }
    )

    # The worker returns the assistant JSON in the last message as a fenced code block.
    content = _extract_final_ai_message_content(result)
    data = _extract_json_block(content)
    assert data is not None, (
        f"Expected JSON in the final assistant message, got: {content}"
    )

    # Validate JSON schema per your spec
    assert "answer" in data and "results" in data
    assert isinstance(data["results"], list) and len(data["results"]) == 3

    # Check that we have the expected results
    result_urls = [r.get("url") for r in data["results"]]
    assert (
        "https://langchain-ai.github.io/langgraph/tutorials/workflows/" in result_urls
    )
    assert (
        "https://medium.com/@vipra_singh/ai-agent-workflow-vs-agent-part-5-2026a890a33d"
        in result_urls
    )
    assert "https://www.louisbouchard.ai/agents-vs-workflows/" in result_urls

    # Check that content is cleaned (no HTML tags)
    for result in data["results"]:
        content = result.get("content", "")
        assert "<" not in content and ">" not in content  # No HTML tags


@pytest.mark.asyncio
async def test_agent_search_no_results(monkeypatch):
    """
    Test search with no results.
    The agent should return an empty results list with appropriate message.
    """
    # Mock empty search results
    mock_search_results = {"organic_results": []}

    class MockGoogleSearch:
        def __init__(self, params):
            self.params = params

        def get_dict(self):
            return mock_search_results

    # Mock the GoogleSearch class and SERPAPI_API_KEY
    monkeypatch.setattr("agents.search.tool_google.GoogleSearch", MockGoogleSearch)
    monkeypatch.setattr("agents.search.tool_google.SERPAPI_API_KEY", "fake_api_key")

    result = await google_search_worker.ainvoke(
        {
            "workers_messages": [
                {
                    "type": "human",
                    "content": "search for nonexistent topic that should return no results",
                }
            ],
        }
    )

    content = _extract_final_ai_message_content(result)
    data = _extract_json_block(content)
    assert data is not None, (
        f"Expected JSON in the final assistant message, got: {content}"
    )

    # Should have empty results list
    assert "results" in data
    assert isinstance(data["results"], list)
    assert len(data["results"]) == 0


@pytest.mark.asyncio
async def test_agent_search_with_html_content(monkeypatch):
    """
    Test search with HTML content that should be cleaned.
    The agent should return clean text without HTML tags.
    """
    # Mock search results with HTML content
    mock_search_results = {
        "organic_results": [
            {
                "link": "https://example.com/article",
                "snippet": "<b>This is bold text</b> and <i>this is italic</i> with <a href='#'>a link</a>",
            }
        ]
    }

    class MockGoogleSearch:
        def __init__(self, params):
            self.params = params

        def get_dict(self):
            return mock_search_results

    # Mock the GoogleSearch class and SERPAPI_API_KEY
    monkeypatch.setattr("agents.search.tool_google.GoogleSearch", MockGoogleSearch)
    monkeypatch.setattr("agents.search.tool_google.SERPAPI_API_KEY", "fake_api_key")

    result = await google_search_worker.ainvoke(
        {
            "workers_messages": [
                {
                    "type": "human",
                    "content": "search for example content",
                }
            ],
        }
    )

    content = _extract_final_ai_message_content(result)
    data = _extract_json_block(content)
    assert data is not None, (
        f"Expected JSON in the final assistant message, got: {content}"
    )

    # Check that HTML tags are removed
    assert len(data["results"]) >= 1
    result_content = data["results"][0].get("content", "")
    assert "<b>" not in result_content
    assert "<i>" not in result_content
    assert "<a href" not in result_content
    assert "This is bold text" in result_content
    assert "this is italic" in result_content


@pytest.mark.asyncio
async def test_agent_search_missing_api_key(monkeypatch):
    """
    Test search when SerpAPI key is missing.
    The agent should return an appropriate error message.
    """
    # Mock missing API key
    monkeypatch.setattr("agents.search.tool_google.SERPAPI_API_KEY", None)

    result = await google_search_worker.ainvoke(
        {
            "workers_messages": [
                {
                    "type": "human",
                    "content": "search for something specific like 'python programming'",
                }
            ],
        }
    )

    content = _extract_final_ai_message_content(result)
    data = _extract_json_block(content)
    
    # The worker might return JSON or a text response when API key is missing
    if data is not None:
        # If JSON is returned, check for error message
        assert "results" in data
        assert isinstance(data["results"], list)
        assert len(data["results"]) == 0
        # The answer should mention the missing API key
        answer = data.get("answer", "").lower()
        assert "serpapi" in answer or "api key" in answer
    else:
        # If text response, check for appropriate message
        assert isinstance(content, str) and len(content) > 0
        # The response should indicate some issue with the search
        assert "search" in content.lower() or "query" in content.lower()


@pytest.mark.asyncio
async def test_agent_search_limited_results(monkeypatch):
    """
    Test search with limited results (less than 3).
    The agent should handle gracefully and return available results.
    """
    # Mock search results with only 2 results
    mock_search_results = {
        "organic_results": [
            {"link": "https://example1.com", "snippet": "First result content"},
            {"link": "https://example2.com", "snippet": "Second result content"},
        ]
    }

    class MockGoogleSearch:
        def __init__(self, params):
            self.params = params

        def get_dict(self):
            return mock_search_results

    # Mock the GoogleSearch class and SERPAPI_API_KEY
    monkeypatch.setattr("agents.search.tool_google.GoogleSearch", MockGoogleSearch)
    monkeypatch.setattr("agents.search.tool_google.SERPAPI_API_KEY", "fake_api_key")

    result = await google_search_worker.ainvoke(
        {
            "workers_messages": [
                {
                    "type": "human",
                    "content": "search for limited results",
                }
            ],
        }
    )

    content = _extract_final_ai_message_content(result)
    data = _extract_json_block(content)
    assert data is not None, (
        f"Expected JSON in the final assistant message, got: {content}"
    )

    # Should have exactly 2 results
    assert "results" in data
    assert isinstance(data["results"], list)
    assert len(data["results"]) == 2

    # Check that we have the expected URLs
    result_urls = [r.get("url") for r in data["results"]]
    assert "https://example1.com" in result_urls
    assert "https://example2.com" in result_urls
