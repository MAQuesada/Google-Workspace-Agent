import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_memory(mock_user_service, orchestrator_graph):
    """
    The assistant should remember the user's name and use it in the response.
    """
    config = {"configurable": {"thread_id": "testing_orchestration_memory"}}
    from utils.config import get_config

    cfg = get_config()
    assert cfg.TESTING == "true"
    response = await orchestrator_graph.ainvoke(
        {
            "user_input": "Hello, My name is Manuel",
            "user_id": "test_user",
        },
        config,
    )

    response = await orchestrator_graph.ainvoke(
        {
            "user_input": "How can you assist me with my task?",
            "user_id": "test_user",
        },
        config,
    )

    response = await orchestrator_graph.ainvoke(
        {
            "user_input": "What is my name?",
            "user_id": "test_user",
        },
        config,
    )
    assert "Manuel" in response["messages"][-1].content, (
        "Response should include the name"
    )
    assert len(response["messages"]) == 6


@pytest.mark.integration
@pytest.mark.asyncio
async def test_memory_2(mock_user_service, orchestrator_graph):
    """
    The assistant after 4 messages interaction should forget the user's name.
    """
    config = {"configurable": {"thread_id": "testing_orchestration_memory_2"}}
    response = await orchestrator_graph.ainvoke(
        {
            "user_input": "Hello, My name is Manuel",
            "user_id": "test_user",
        },
        config,
    )

    assert "Manuel" in response["messages"][-1].content, (
        "Response should include the name"
    )

    response = await orchestrator_graph.ainvoke(  # 1
        {
            "user_input": "In which task can you assist me?",
            "user_id": "test_user",
        },
        config,
    )
    assert "Manuel" not in response["messages"][-1].content, (
        "Response should not include the name"
    )

    response = await orchestrator_graph.ainvoke(  # 2
        {
            "user_input": "...",
            "user_id": "test_user",
        },
        config,
    )
    assert "Manuel" not in response["messages"][-1].content, (
        "Response should include the name"
    )
    response = await orchestrator_graph.ainvoke(  # 3
        {
            "user_input": "...",
            "user_id": "test_user",
        },
        config,
    )
    assert "Manuel" not in response["messages"][-1].content, (
        "Response should not include the name"
    )
    response = await orchestrator_graph.ainvoke(  # 4
        {
            "user_input": "Do you know my name?",
            "user_id": "test_user",
        },
        config,
    )
    assert "Manuel" not in response["messages"][-1].content, (
        "Response should not include the name"
    )
    assert len(response["messages"]) == 10
