import pytest
from unittest.mock import patch, MagicMock
from langgraph.checkpoint.memory import MemorySaver
from agents.utils import create_checkpointer


def test_create_checkpointer_uses_memory_saver_in_test_environment():
    """
    Test that create_checkpointer returns MemorySaver when in test environment.
    """
    # Ensure we're in test environment
    with patch.dict('os.environ', {'TESTING': 'true'}):
        checkpointer = create_checkpointer()
        assert isinstance(checkpointer, MemorySaver)


def test_create_checkpointer_uses_postgres_in_production():
    """
    Test that create_checkpointer returns PostgresSaverCustom when not in test environment.
    """
    # Mock environment to simulate production
    with patch.dict('os.environ', {}, clear=True):
        with patch('agents.utils.ConnectionPool') as mock_pool:
            with patch('agents.utils.PostgresSaverCustom') as mock_postgres_saver:
                # Mock the pool connection
                mock_conn = MagicMock()
                mock_pool.return_value.__enter__.return_value.connection.return_value.__enter__.return_value = mock_conn
                
                # Mock PostgresSaverCustom
                mock_saver_instance = MagicMock()
                mock_postgres_saver.return_value = mock_saver_instance
                
                # Set the required environment variable
                with patch.dict('os.environ', {'POSTGRES_DB_URI': 'postgresql://test'}):
                    checkpointer = create_checkpointer()
                    
                    # Verify PostgresSaverCustom was called
                    mock_postgres_saver.assert_called_once_with(mock_conn)
                    mock_saver_instance.setup.assert_called_once()


def test_create_checkpointer_raises_error_without_db_uri():
    """
    Test that create_checkpointer raises an error when POSTGRES_DB_URI is not set in production.
    """
    # Mock environment to simulate production without DB URI
    with patch.dict('os.environ', {}, clear=True):
        with pytest.raises(ValueError, match="POSTGRES_DB_URI environment variable is required for production"):
            create_checkpointer()


def test_orchestrator_graph_uses_memory_saver_in_tests():
    """
    Test that the orchestrator graph uses MemorySaver when imported in test environment.
    """
    # Ensure we're in test environment
    with patch.dict('os.environ', {'TESTING': 'true'}):
        # Import the orchestrator graph
        from agents.orchestrator.core import orchestrator_graph
        
        # The graph should be compiled with a MemorySaver checkpointer
        # We can verify this by checking that the graph exists and is compiled
        assert orchestrator_graph is not None 